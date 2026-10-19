#!/usr/bin/env Rscript
# Empirical approach/departure envelopes for SBGR and SBSP from Flightradar24 tracks
# ==================================================================================
# Usage:
#   Rscript generate_approach_surfaces_fr24.R <fr24_dir> [out_dir]
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
#      half-plane are assigned to stations every 0.1 NM of radial distance up to 10 NM, keeping
#      the nearest sample of each flight. Stations need at least 5 flights.
#   4. At each station: 5th (P5) and 95th (P95) altitude percentiles and the P95 of the absolute
#      cross-axis deviation, each smoothed with a cubic spline (spar = 0.5).
#   5. Each cross-section is centred on the extended runway axis, 2 x the lateral percentile
#      wide, and bounded vertically by the smoothed P5 and P95.
#
# Outputs in <out_dir> (default: data/ next to this script):
#   approach_surfaces_<ICAO>.csv     dashboard route files (route, id, name, lat, lon, type,
#                                    altitude, height, width; metres). One route per side;
#                                    altitude is the P5-P95 mid-point and height the band
#                                    thickness, because the dashboard centres volumes on altitude.
#   approach_surfaces_stations.csv   per-station statistics (raw and smoothed)
#   approach_surfaces_summary.csv    flights and extent per side

suppressMessages(library(dplyr))

args <- commandArgs(trailingOnly = TRUE)
if (length(args) < 1) stop("Usage: Rscript generate_approach_surfaces_fr24.R <fr24_dir> [out_dir]")
FR24_DIR <- args[1]
script_arg <- grep("^--file=", commandArgs(FALSE), value = TRUE)
script_dir <- if (length(script_arg)) dirname(normalizePath(sub("^--file=", "", script_arg))) else getwd()
OUT_DIR <- if (length(args) >= 2) args[2] else file.path(script_dir, "data")
dir.create(OUT_DIR, showWarnings = FALSE, recursive = TRUE)

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

  # Local runway-axis frame centred on the ARP (NM)
  H <- a$axis * pi / 180
  traj <- traj %>% mutate(
    e = (lon - a$lon) * cos(a$lat * pi / 180) * 60, n = (lat - a$lat) * 60,
    s = e * sin(H) + n * cos(H),          # along-axis, positive towards the axis heading
    c = e * cos(H) - n * sin(H))          # cross-axis, positive to the right of the axis heading

  for (sgn in c(1, -1)) {
    side <- if (sgn > 0) a$pos_side else a$neg_side
    bearing <- if (sgn > 0) a$axis else (a$axis + 180) %% 360
    st <- traj %>% mutate(r = sqrt(e^2 + n^2)) %>%
      filter(sgn * s >= 0, r <= MAX_DISTANCE_NM + 0.05) %>%
      mutate(k = round(r / DISTANCE_STEP_NM), err = abs(r - k * DISTANCE_STEP_NM)) %>%
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
    ll <- t(sapply(bands$distance_nm, function(d) dest_point(a$lat, a$lon, bearing, d)))
    bands <- bands %>% mutate(lat = ll[, "lat"], lon = ll[, "lon"], icao = icao, side = side, bearing = bearing)
    station_rows[[length(station_rows) + 1]] <- bands

    flights_side <- st %>% distinct(indicat, flow, rwy)
    summary_rows[[length(summary_rows) + 1]] <- tibble(
      icao = icao, side = side, bearing = bearing, stations = nrow(bands),
      flights = nrow(flights_side),
      arrivals = sum(flights_side$flow == "ARR"), departures = sum(flights_side$flow == "DEP"),
      lo_ft_min = round(min(bands$lo_m) / FT), hi_ft_max = round(max(bands$hi_m) / FT),
      width_nm_max = round(2 * max(bands$lat_s), 2))
  }

  out <- bind_rows(station_rows) %>% filter(icao == !!icao) %>% group_by(side) %>%
    mutate(id = row_number()) %>% ungroup() %>%
    transmute(route = side, id, name = sprintf("%s_Node%d", side, id), lat, lon, type = "Node",
              altitude = (lo_m + hi_m) / 2, height = pmax(0.001, hi_m - lo_m),
              width = 2 * lat_s * 1852)
  write.csv(out, file.path(OUT_DIR, sprintf("approach_surfaces_%s.csv", icao)), row.names = FALSE)

  cat(sprintf("\n%s: %d flights with runway heading (ARR %d, DEP %d)\n", icao,
              n_distinct(traj$indicat), n_distinct(traj$indicat[traj$flow == "ARR"]),
              n_distinct(traj$indicat[traj$flow == "DEP"])))
  print(traj %>% distinct(indicat, flow, rwy) %>% count(flow, rwy))
}

summ <- bind_rows(summary_rows)
print(summ)
write.csv(summ, file.path(OUT_DIR, "approach_surfaces_summary.csv"), row.names = FALSE)
stations <- bind_rows(station_rows) %>%
  transmute(icao, side, bearing_deg = bearing, station = k, distance_nm, lat, lon, n_flights,
            p5_alt_m = p5_m, p95_alt_m = p95_m, mean_alt_m = mean_m,
            p95_abs_lateral_nm = lat_p95_nm, p5_lateral_nm = c_p5_nm, p95_lateral_nm = c_p95_nm,
            lower_limit_m = lo_m, upper_limit_m = hi_m, half_width_nm = lat_s)
write.csv(stations, file.path(OUT_DIR, "approach_surfaces_stations.csv"), row.names = FALSE)
cat("Done.\n")
