#!/usr/bin/env Rscript
# Empirical approach/departure envelopes for SBGR and SBSP from Flightradar24 tracks
# ==================================================================================
# Usage:
#   Rscript generate_approach_surfaces_fr24.R <fr24_dir> [out_dir] [--stations=radial|stream]
#
# The default (--stations=radial) reproduces the published envelopes, one per side of the
# airport. --stations=stream builds one envelope per direction-resolved traffic stream instead
# (see "Stream envelopes" below); its outputs carry the suffix _stream, so the published files
# are never overwritten. Releases ridita-2026 and ridita-2026.1 also had an along-axis variant
# (--stations=axis --lateral=traffic --align=30); it was removed because it pooled the traffic
# streams that share a side of the airport into irregular cross-sections.
#
# <fr24_dir> holds one .Rda file per day, each containing a data frame `df` with one row per
# track sample and the columns
#   indicat   flight identifier
#   time      sample time (sortable)
#   phase     flight phase; ARR_40 / GND_ARR (arrival) and DEP_40 / GND_DEP (departure) are used
#   lat, lon  WGS84 position (degrees)
#   alt       barometric altitude (ft); 0 on the ground
#   head      heading (degrees)
#   plan_dep, plan_arr  planned departure and arrival aerodromes (ICAO)
# The published envelopes used December 2022 (31 days). Raw Flightradar24 data are licensed and
# are not distributed with this repository.
#
# Method, per airport:
#   1. Keep arrivals (ARR_40, GND_ARR) and departures (DEP_40, GND_DEP) within 0.3 deg of the
#      airport, trimming ground samples at touchdown (first zero altitude) and lift-off (last
#      zero altitude). The heading at those samples identifies the runway direction; parallel
#      runways are grouped.
#   2. Airborne altitudes are used as reported (barometric, no QNH correction); on-ground zeros
#      take the field elevation.
#   3. For each side of the airport reference point (ARP) along the runway axis, samples in that
#      half-plane within 10 NM of the ARP are assigned to stations every 0.1 NM of radial
#      distance, keeping the nearest sample of each flight; stations need at least 5 flights.
#      Stations are placed on the extended runway axis at that distance, so a sample flown off
#      the axis is assigned to a station farther out than its along-axis position.
#   4. At each station: 5th (P5) and 95th (P95) altitude percentiles and the P95 of the absolute
#      cross-axis offset, each smoothed with a cubic spline (spar = 0.5).
#   5. Each cross-section is bounded vertically by the smoothed P5 and P95 altitudes, centered on
#      the extended runway axis and 2 x the smoothed absolute-offset P95 wide.
#
# Stream envelopes (--stations=stream), per airport, after steps 1 and 2:
#   S1. Each flight's last pass through the 10-NM circle around the ARP (arrivals: up to
#       touchdown; departures: from lift-off), ordered from the runway outwards.
#   S2. Per flow (ARR, DEP) and runway direction, the paths, resampled along their length, are
#       clustered with k-means into streams (e.g. a straight-in final and a circuit joining it).
#   S3. Each stream gets stations every 0.1 NM along its mean path; at each station, the P5 and P95
#       altitude and signed cross-path offset of its flights (nearest sample per flight), smoothed
#       along the path (about one spline degree of freedom per NM).
#   S4. Each cross-section is bounded by the smoothed P5 and P95 altitudes and spans the smoothed
#       P5-P95 lateral band, centered on the stream.
#
# Outputs in <out_dir> (default: data/ next to this script):
#   approach_surfaces_<ICAO>.csv     dashboard route files (route, id, name, lat, lon, type,
#                                    altitude, height, width; meters). One route per side (one
#                                    per stream with --stations=stream, e.g. ARR17_S1); altitude
#                                    is the P5-P95 mid-point and height the band thickness,
#                                    because the dashboard centers volumes on altitude.
#   approach_surfaces_stations.csv   per-station statistics (raw and smoothed)
#   approach_surfaces_summary.csv    flights and extent per side (per stream)

suppressMessages(library(dplyr))

all_args <- commandArgs(trailingOnly = TRUE)
opt_value <- function(name, default, allowed) {
  hit <- grep(paste0("^--", name, "="), all_args, value = TRUE)
  value <- if (length(hit)) sub(paste0("^--", name, "="), "", hit[length(hit)]) else default
  if (!value %in% allowed) stop(sprintf("--%s must be one of: %s", name, paste(allowed, collapse = ", ")))
  value
}
unknown <- setdiff(sub("=.*", "", grep("^--", all_args, value = TRUE)), "--stations")
if (length(unknown)) stop(sprintf("Unknown option(s): %s (the along-axis options --stations=axis, --lateral and --align were removed after release ridita-2026.1)",
                                  paste(unknown, collapse = ", ")))
STATIONS <- opt_value("stations", "radial", c("radial", "stream"))
args <- all_args[!grepl("^--", all_args)]
if (length(args) < 1) stop("Usage: Rscript generate_approach_surfaces_fr24.R <fr24_dir> [out_dir] [--stations=radial|stream]")
FR24_DIR <- args[1]
script_arg <- grep("^--file=", commandArgs(FALSE), value = TRUE)
script_dir <- if (length(script_arg)) dirname(normalizePath(sub("^--file=", "", script_arg))) else getwd()
OUT_DIR <- if (length(args) >= 2) args[2] else file.path(script_dir, "data")
dir.create(OUT_DIR, showWarnings = FALSE, recursive = TRUE)
SUFFIX <- if (STATIONS == "stream") "_stream" else ""
cat(if (STATIONS == "stream") "Stations: along the mean path of each direction-resolved stream\n" else
  "Stations: radial distance from the ARP, per side of the airport\n")

DISTANCE_STEP_NM <- 0.1
MAX_DISTANCE_NM <- 10.0
MIN_POINTS <- 5
PERCENTILE_P <- 0.05
SMOOTHING_SPL <- 0.5
FT <- 0.3048

# ARP, runway axis heading (true, degrees) and field elevation
airports <- list(
  SBGR = list(lat = -23.4356, lon = -46.4731, axis = 74,  elev_m = 2461 * FT,
              pos_side = "SIDE_10", neg_side = "SIDE_28", rwy = c(10, 28)),
  SBSP = list(lat = -23.6261, lon = -46.6564, axis = 147, elev_m = 2631 * FT,
              pos_side = "SIDE_17", neg_side = "SIDE_35", rwy = c(17, 35))
)

hdiff <- function(a, b) { d <- abs(a - b) %% 360; pmin(d, 360 - d) }

dest_point <- function(lat, lon, bearing_deg, dist_nm) {
  la <- lat * pi / 180; lo <- lon * pi / 180; b <- bearing_deg * pi / 180; d <- dist_nm / 3440.065
  la2 <- asin(sin(la) * cos(d) + cos(la) * sin(d) * cos(b))
  lo2 <- lo + atan2(sin(b) * sin(d) * cos(la), cos(d) - sin(la) * sin(la2))
  c(lat = la2 * 180 / pi, lon = lo2 * 180 / pi)
}

smooth_col <- function(x, y) {
  if (length(x) < 4) return(y)
  predict(smooth.spline(x, y, spar = SMOOTHING_SPL), x)$y
}

# ------------------------------------------------------------------------------------------
# Direction-resolved ("stream") envelopes, --stations=stream
# ------------------------------------------------------------------------------------------
# Each flight's last pass through the circle of STREAM_RADIUS_NM around the ARP (arrivals: up to
# touchdown; departures: from lift-off) is resampled along its length. Per flow and runway
# direction, the paths are clustered with k-means; k is the largest value (up to STREAM_K_MAX)
# whose streams each carry at least STREAM_MIN_SHARE of the flights and whose mean paths are at
# least STREAM_MIN_SEP_NM apart on average. Each stream gets stations every DISTANCE_STEP_NM along
# its mean path, from the runway outwards; at each station, the P5/P95 altitude and signed
# cross-path offset of its flights (nearest sample per flight) are smoothed with about one spline
# degree of freedom per STREAM_SMOOTH_NM of path, the width on a log scale so it stays positive;
# each smoothed center and width is kept within the raw values within LOCAL_RANGE_NM of its
# station (no overshoot or collapse at abrupt changes). Raw widths below MIN_WIDTH_NM (a
# numerical guard) are raised to it.
MIN_WIDTH_NM <- 0.001
LOCAL_RANGE_NM <- 1.0
STREAM_RADIUS_NM <- 10
STREAM_FEATURE_POINTS <- 16
STREAM_REF_POINTS <- 80
STREAM_K_MAX <- 6
STREAM_MIN_SHARE <- 0.05
STREAM_MIN_SEP_NM <- 1.5
STREAM_MIN_PATH_NM <- 2
STREAM_SMOOTH_NM <- 1.0

resample_path <- function(x, y, k) {
  s <- c(0, cumsum(sqrt(diff(x)^2 + diff(y)^2)))
  keep <- !duplicated(s)
  if (sum(keep) < 2) return(NULL)
  s <- s[keep]; x <- x[keep]; y <- y[keep]
  t <- seq(0, s[length(s)], length.out = k)
  cbind(approx(s, x, t)$y, approx(s, y, t)$y)
}

smooth_len <- function(x, y) {
  if (length(x) < 6) return(y)
  df <- max(4, min(length(x) - 2, diff(range(x)) / STREAM_SMOOTH_NM))
  predict(smooth.spline(x, y, df = df), x)$y
}

smooth_stream_lateral <- function(x, v5, v95) {
  stopifnot(all(is.finite(v5)), all(is.finite(v95)), all(v95 >= v5))
  mid <- (v5 + v95) / 2; w <- pmax(v95 - v5, MIN_WIDTH_NM)
  near <- lapply(x, function(xi) which(abs(x - xi) <= LOCAL_RANGE_NM + 1e-9))
  bound <- function(s, raw) pmin(pmax(s, sapply(near, function(k) min(raw[k]))), sapply(near, function(k) max(raw[k])))
  list(centre = bound(smooth_len(x, mid), mid), width = bound(exp(smooth_len(x, log(w))), w))
}

# Last pass of each flight through the circle, ordered from the runway outwards
stream_paths <- function(traj) {
  traj <- traj[order(traj$indicat, traj$time), ]
  paths <- lapply(split(seq_len(nrow(traj)), traj$indicat), function(ii) {
    g <- traj[ii, ]
    out <- which(sqrt(g$e^2 + g$n^2) > STREAM_RADIUS_NM)
    if (g$flow[1] == "ARR") {
      if (length(out)) g <- g[(max(out) + 1):nrow(g), , drop = FALSE]
      g <- g[rev(seq_len(nrow(g))), , drop = FALSE]
    } else if (length(out)) {
      g <- g[seq_len(min(out) - 1), , drop = FALSE]
    }
    if (nrow(g) < 5 || sum(sqrt(diff(g$e)^2 + diff(g$n)^2)) < STREAM_MIN_PATH_NM) return(NULL)
    feat <- resample_path(g$e, g$n, STREAM_FEATURE_POINTS)
    ref <- resample_path(g$e, g$n, STREAM_REF_POINTS)
    if (is.null(feat) || is.null(ref)) return(NULL)
    list(g = g, feat = c(feat[, 1], feat[, 2]), ref = ref, flow = g$flow[1], rwy = g$rwy[1])
  })
  paths[!vapply(paths, is.null, TRUE)]
}

choose_streams <- function(features) {
  best <- rep(1L, nrow(features)); best_k <- 1L
  if (STREAM_K_MAX < 2) return(list(cluster = best, k = best_k))
  kf <- STREAM_FEATURE_POINTS
  for (k in 2:STREAM_K_MAX) {
    if (nrow(features) < 20 * k) break
    # 20 random starts: with 5, the number of streams found for SBGR runway 28 departures
    # (December 2022) depended on the seed
    set.seed(1)
    km <- kmeans(features, centers = k, nstart = 20, iter.max = 50)
    share <- tabulate(km$cluster, k) / nrow(features)
    cen <- km$centers
    sep <- min(apply(combn(k, 2), 2, function(p) mean(sqrt((cen[p[1], 1:kf] - cen[p[2], 1:kf])^2 +
                                                        (cen[p[1], kf + 1:kf] - cen[p[2], kf + 1:kf])^2))))
    if (min(share) >= STREAM_MIN_SHARE && sep >= STREAM_MIN_SEP_NM) { best <- km$cluster; best_k <- k }
  }
  # number the streams by size
  rank <- order(order(-tabulate(best, best_k)))
  list(cluster = rank[best], k = best_k)
}

# Stations along a stream's mean path (distance from the runway end, NM)
stream_bands <- function(members, a) {
  ref <- Reduce(`+`, lapply(members, `[[`, "ref")) / length(members)
  seg <- diff(ref); seglen <- sqrt(rowSums(seg^2)); cum <- c(0, cumsum(seglen))
  A <- ref[-nrow(ref), , drop = FALSE]
  proj <- bind_rows(lapply(members, function(f) {
    P <- cbind(f$g$e, f$g$n); m <- nrow(P)
    sx <- rep(seg[, 1], each = m); sy <- rep(seg[, 2], each = m)
    ax <- rep(A[, 1], each = m); ay <- rep(A[, 2], each = m)
    t <- pmin(pmax(((P[, 1] - ax) * sx + (P[, 2] - ay) * sy) / rep(seglen^2, each = m), 0), 1)
    d2 <- matrix((P[, 1] - ax - t * sx)^2 + (P[, 2] - ay - t * sy)^2, nrow = m)
    j <- max.col(-d2, ties.method = "first"); ij <- cbind(seq_len(m), j)
    tj <- matrix(t, nrow = m)[ij]
    side <- sign(seg[j, 1] * (P[, 2] - A[j, 2]) - seg[j, 2] * (P[, 1] - A[j, 1]))   # > 0: left of the path
    data.frame(indicat = f$g$indicat[1], u = cum[j] + tj * seglen[j], v = side * sqrt(d2[ij]), alt = f$g$alt_msl_m)
  }))
  bands <- proj %>% mutate(k = round(u / DISTANCE_STEP_NM), err = abs(u - k * DISTANCE_STEP_NM)) %>%
    group_by(indicat, k) %>% slice_min(err, n = 1, with_ties = FALSE) %>% ungroup() %>%
    group_by(k) %>% summarise(
      n_flights = n(),
      p5_m = quantile(alt, PERCENTILE_P, names = FALSE), p95_m = quantile(alt, 1 - PERCENTILE_P, names = FALSE),
      v_p5_nm = quantile(v, PERCENTILE_P, names = FALSE), v_p95_nm = quantile(v, 1 - PERCENTILE_P, names = FALSE),
      .groups = "drop") %>%
    filter(n_flights >= MIN_POINTS, k * DISTANCE_STEP_NM <= max(cum)) %>% arrange(k) %>%
    mutate(distance_nm = k * DISTANCE_STEP_NM, p5_s = smooth_len(distance_nm, p5_m), p95_s = smooth_len(distance_nm, p95_m),
           lo_m = pmin(p5_s, p95_s), hi_m = pmax(p5_s, p95_s))
  if (!nrow(bands)) return(NULL)
  lateral <- smooth_stream_lateral(bands$distance_nm, bands$v_p5_nm, bands$v_p95_nm)
  # station: point of the mean path shifted by the band center along the left normal
  mid_u <- cum[-1] - seglen / 2
  ux <- approx(mid_u, seg[, 1] / seglen, bands$distance_nm, rule = 2)$y
  uy <- approx(mid_u, seg[, 2] / seglen, bands$distance_nm, rule = 2)$y
  nn <- sqrt(ux^2 + uy^2)
  e <- approx(cum, ref[, 1], bands$distance_nm, rule = 2)$y - uy / nn * lateral$centre
  n <- approx(cum, ref[, 2], bands$distance_nm, rule = 2)$y + ux / nn * lateral$centre
  bands %>% mutate(centre_nm = lateral$centre, width_nm = lateral$width,
                   lat = a$lat + n / 60, lon = a$lon + e / (60 * cos(a$lat * pi / 180)), path_nm = max(cum))
}

stream_envelopes <- function(traj, a, icao) {
  paths <- stream_paths(traj)
  key <- vapply(paths, function(f) sprintf("%s%02d", f$flow, as.integer(f$rwy)), "")
  stations <- list(); summary <- list()
  for (grp in sort(unique(key))) {
    members <- paths[key == grp]
    cl <- choose_streams(do.call(rbind, lapply(members, `[[`, "feat")))
    for (j in seq_len(cl$k)) {
      mem <- members[cl$cluster == j]
      name <- sprintf("%s_S%d", grp, j)
      b <- stream_bands(mem, a)
      if (is.null(b)) {
        cat(sprintf("  %s %s: no station with %d flights; stream skipped\n", icao, name, MIN_POINTS))
        next
      }
      b <- b %>% mutate(icao = icao, stream = name, flow = substr(grp, 1, 3), runway = substr(grp, 4, 5))
      stations[[length(stations) + 1]] <- b
      summary[[length(summary) + 1]] <- tibble(
        icao = icao, stream = name, flow = substr(grp, 1, 3), runway = substr(grp, 4, 5), flights = length(mem),
        share_of_group = round(length(mem) / length(members), 3), group_flights = length(members), streams_in_group = cl$k,
        path_nm = round(b$path_nm[1], 1), stations = nrow(b), lo_ft_min = round(min(b$lo_m) / FT), hi_ft_max = round(max(b$hi_m) / FT),
        width_nm_median = round(median(b$width_nm), 2), width_nm_max = round(max(b$width_nm), 2))
    }
  }
  list(stations = stations, summary = summary, flights_in_streams = length(paths))
}

# ------------------------------------------------------------------------------------------
# Load the daily files, keeping only the samples needed for the two airports
# ------------------------------------------------------------------------------------------
rda_files <- list.files(FR24_DIR, pattern = "[.]Rda$", full.names = TRUE)
if (!length(rda_files)) stop("No .Rda files found in ", FR24_DIR)
cat(sprintf("Found %d daily files\n", length(rda_files)))
parts <- list()
for (f in rda_files) {
  env <- new.env(); load(f, envir = env); d <- get("df", envir = env)
  for (icao in names(airports)) {
    a <- airports[[icao]]
    parts[[length(parts) + 1]] <- d %>%
      filter(abs(lat - a$lat) < 0.3, abs(lon - a$lon) < 0.3,
             (plan_arr == icao & phase %in% c("ARR_40", "GND_ARR")) |
             (plan_dep == icao & phase %in% c("DEP_40", "GND_DEP"))) %>%
      transmute(icao = icao, indicat, time, phase, lat, lon, alt, head,
                flow = ifelse(plan_arr == icao & phase %in% c("ARR_40", "GND_ARR"), "ARR", "DEP"))
  }
  cat(sprintf("  %s\n", basename(f))); rm(d, env); invisible(gc())
}
all_pts <- bind_rows(parts); rm(parts)

summary_rows <- list(); station_rows <- list()

for (icao in names(airports)) {
  a <- airports[[icao]]
  pts <- all_pts %>% filter(icao == !!icao) %>% arrange(indicat, time)

  # Ground-sample trimming and runway heading at touchdown / lift-off
  arr <- pts %>% filter(flow == "ARR") %>% group_by(indicat) %>%
    mutate(rn = row_number(), z = phase == "GND_ARR" & alt == 0,
           first_z = ifelse(any(z), min(which(z)), Inf),
           rwy_head = if (any(z)) head[which(z)[1]] else NA_real_) %>%
    filter(phase == "ARR_40" | (phase == "GND_ARR" & rn <= first_z)) %>% ungroup()
  dep <- pts %>% filter(flow == "DEP") %>% group_by(indicat) %>%
    mutate(rn = row_number(), z = phase == "GND_DEP" & alt == 0,
           first_z = ifelse(any(z), min(which(z)), Inf),
           rwy_head = if (any(z)) head[max(which(z))] else NA_real_) %>%
    filter(phase == "DEP_40" | (phase == "GND_DEP" & rn >= first_z)) %>% ungroup()
  traj <- bind_rows(arr, dep) %>% filter(!is.na(rwy_head)) %>%
    mutate(rwy = ifelse(hdiff(rwy_head, a$axis) <= hdiff(rwy_head, a$axis + 180), a$rwy[1], a$rwy[2]),
           alt_msl_m = ifelse(alt == 0, a$elev_m, alt * FT))

  # Local runway-axis frame centered on the ARP (NM)
  H <- a$axis * pi / 180
  traj <- traj %>% mutate(
    e = (lon - a$lon) * cos(a$lat * pi / 180) * 60, n = (lat - a$lat) * 60,
    s = e * sin(H) + n * cos(H),          # along-axis, positive toward the axis heading
    c = e * cos(H) - n * sin(H))          # cross-axis, positive to the right of the axis heading

  if (STATIONS == "stream") {
    res <- stream_envelopes(traj, a, icao)
    if (!length(res$stations)) {
      cat(sprintf("\n%s: no stream with %d flights; airport skipped\n", icao, MIN_POINTS))
      next
    }
    station_rows <- c(station_rows, res$stations); summary_rows <- c(summary_rows, res$summary)
    out <- bind_rows(res$stations) %>% group_by(stream) %>% mutate(id = row_number()) %>% ungroup() %>%
      transmute(route = stream, id, name = sprintf("%s_Node%d", stream, id), lat, lon, type = "Node",
                altitude = (lo_m + hi_m) / 2, height = pmax(0.001, hi_m - lo_m), width = width_nm * 1852)
    write.csv(out, file.path(OUT_DIR, sprintf("approach_surfaces_%s%s.csv", icao, SUFFIX)), row.names = FALSE)
    cat(sprintf("\n%s: %d flights with runway heading, %d in %d streams\n", icao, n_distinct(traj$indicat),
                res$flights_in_streams, length(res$summary)))
    next
  }

  for (sgn in c(1, -1)) {
    side <- if (sgn > 0) a$pos_side else a$neg_side
    bearing <- if (sgn > 0) a$axis else (a$axis + 180) %% 360
    # Station distance: radial distance from the ARP (within 10 NM), on this side of the airport
    st <- traj %>% mutate(dist = sqrt(e^2 + n^2)) %>%
      filter(sgn * s >= 0, dist <= MAX_DISTANCE_NM + 0.05) %>%
      mutate(k = round(dist / DISTANCE_STEP_NM), err = abs(dist - k * DISTANCE_STEP_NM)) %>%
      group_by(indicat, k) %>% slice_min(err, n = 1, with_ties = FALSE) %>% ungroup()
    bands <- st %>% group_by(k) %>% summarise(
      n_flights = n(),
      p5_m = quantile(alt_msl_m, PERCENTILE_P, names = FALSE),
      p95_m = quantile(alt_msl_m, 1 - PERCENTILE_P, names = FALSE),
      mean_m = mean(alt_msl_m),
      lat_p95_nm = quantile(abs(c), 1 - PERCENTILE_P, names = FALSE),
      c_p5_nm = quantile(c, PERCENTILE_P, names = FALSE),
      c_p95_nm = quantile(c, 1 - PERCENTILE_P, names = FALSE), .groups = "drop") %>%
      filter(n_flights >= MIN_POINTS) %>% arrange(k) %>%
      mutate(distance_nm = k * DISTANCE_STEP_NM,
             p5_s = smooth_col(distance_nm, p5_m),
             p95_s = smooth_col(distance_nm, p95_m),
             lat_s = pmax(0.001, smooth_col(distance_nm, lat_p95_nm)),
             lo_m = pmin(p5_s, p95_s), hi_m = pmax(p5_s, p95_s))
    if (nrow(bands) == 0) {
      cat(sprintf("  %s %s: no station with %d flights; side skipped\n", icao, side, MIN_POINTS))
      next
    }
    bands <- bands %>% mutate(width_nm = 2 * lat_s)
    ll <- t(sapply(bands$distance_nm, function(d) dest_point(a$lat, a$lon, bearing, d)))
    bands <- bands %>% mutate(lat = ll[, "lat"], lon = ll[, "lon"], icao = icao, side = side, bearing = bearing)
    station_rows[[length(station_rows) + 1]] <- bands

    flights_side <- st %>% distinct(indicat, flow, rwy)
    summary_rows[[length(summary_rows) + 1]] <- tibble(
      icao = icao, side = side, bearing = bearing, stations = nrow(bands),
      flights = nrow(flights_side),
      arrivals = sum(flights_side$flow == "ARR"), departures = sum(flights_side$flow == "DEP"),
      lo_ft_min = round(min(bands$lo_m) / FT), hi_ft_max = round(max(bands$hi_m) / FT),
      width_nm_max = round(max(bands$width_nm), 2))
  }

  out <- bind_rows(station_rows) %>% filter(icao == !!icao) %>% group_by(side) %>%
    mutate(id = row_number()) %>% ungroup() %>%
    transmute(route = side, id, name = sprintf("%s_Node%d", side, id), lat, lon, type = "Node",
              altitude = (lo_m + hi_m) / 2, height = pmax(0.001, hi_m - lo_m),
              width = width_nm * 1852)
  write.csv(out, file.path(OUT_DIR, sprintf("approach_surfaces_%s%s.csv", icao, SUFFIX)), row.names = FALSE)

  cat(sprintf("\n%s: %d flights with runway heading (ARR %d, DEP %d)\n", icao,
              n_distinct(traj$indicat), n_distinct(traj$indicat[traj$flow == "ARR"]),
              n_distinct(traj$indicat[traj$flow == "DEP"])))
  print(traj %>% distinct(indicat, flow, rwy) %>% count(flow, rwy))
}

summ <- bind_rows(summary_rows)
print(as.data.frame(summ))
write.csv(summ, file.path(OUT_DIR, sprintf("approach_surfaces_summary%s.csv", SUFFIX)), row.names = FALSE)
if (STATIONS == "stream") {
  stations <- bind_rows(station_rows) %>%
    transmute(icao, stream, flow, runway, station = k, distance_along_path_nm = distance_nm, lat, lon, n_flights,
              p5_alt_m = p5_m, p95_alt_m = p95_m, p5_lateral_nm = v_p5_nm, p95_lateral_nm = v_p95_nm,
              lower_limit_m = lo_m, upper_limit_m = hi_m, centre_offset_nm = centre_nm, width_nm)
  write.csv(stations, file.path(OUT_DIR, sprintf("approach_surfaces_stations%s.csv", SUFFIX)), row.names = FALSE)
  cat("Done.\n")
  quit(save = "no")
}
stations <- bind_rows(station_rows) %>%
  transmute(icao, side, bearing_deg = bearing, station = k, distance_nm, lat, lon, n_flights,
            p5_alt_m = p5_m, p95_alt_m = p95_m, mean_alt_m = mean_m,
            p95_abs_lateral_nm = lat_p95_nm, p5_lateral_nm = c_p5_nm, p95_lateral_nm = c_p95_nm,
            lower_limit_m = lo_m, upper_limit_m = hi_m, half_width_nm = lat_s)
write.csv(stations, file.path(OUT_DIR, sprintf("approach_surfaces_stations%s.csv", SUFFIX)), row.names = FALSE)
cat("Done.\n")
