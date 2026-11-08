# Flightradar24 track selection and quality control shared by tools/generate_approach_surfaces_fr24.R
# and ridita2026/scripts/extract_tracks.R (source this file; requires dplyr).
#
# Per airport, arrivals (ARR_40, GND_ARR) and departures (DEP_40, GND_DEP) within 0.3 deg of the
# airport reference point (ARP) are kept, then:
#   1. Exact copies of a sample are kept once (the daily files overlap in time).
#   2. Synthetic phase-boundary points are removed. The source data contain, for each flight, one
#      point where it crosses 1 NM from the airport, stored under both phases (GND_* and *_40) at
#      the same time and position, with altitude, speed and heading interpolated between the
#      adjacent samples. When one neighbor is a ground sample (altitude 0), the interpolated
#      altitude lies hundreds of feet below the runway (SBGR, December 2022: 2,971 of 20,985
#      points more than 300 ft below the field elevation). These points are not observations.
#   3. Ground samples are trimmed at touchdown (arrivals: up to the first zero altitude) and
#      lift-off (departures: from the last zero altitude). The heading at that sample identifies
#      the runway direction; parallel runways are grouped.
#   4. Altitudes. Flightradar24 altitudes are pressure altitudes (standard setting, 1013.25 hPa).
#      With a QNH table (read_qnh()), airborne altitudes are converted to altitudes above mean sea
#      level with the QNH of the airport's METAR nearest in time (ICAO standard atmosphere);
#      without one they are used as reported. On-ground zeros take the field elevation.
#   5. Airborne samples more than LOW_LIMIT_FT below the field elevation are physically
#      implausible and are removed (counted in the QC table).
FT <- 0.3048
LOW_LIMIT_FT <- 300
QNH_MAX_GAP_H <- 3

# Pressure altitude (ft) -> altitude above the QNH datum (ft), ICAO standard atmosphere
pressure_to_qnh_altitude <- function(pa_ft, qnh_hpa) {
  k <- 145366.45; x <- 0.190284
  p <- 1013.25 * (1 - pa_ft / k)^(1 / x)
  k * (1 - (p / qnh_hpa)^x)
}

# QNH table: CSV with columns station (ICAO), valid_utc ("YYYY-MM-DD HH:MM") and qnh_hpa
read_qnh <- function(path) {
  q <- read.csv(path, stringsAsFactors = FALSE)
  stopifnot(all(c("station", "valid_utc", "qnh_hpa") %in% names(q)))
  q %>% transmute(station, time = as.POSIXct(valid_utc, tz = "UTC"), qnh_hpa = as.numeric(qnh_hpa)) %>%
    filter(!is.na(time), is.finite(qnh_hpa)) %>% arrange(station, time)
}

# QNH of the METAR nearest in time (within QNH_MAX_GAP_H hours), else NA
nearest_qnh <- function(time, q) {
  if (!nrow(q)) return(rep(NA_real_, length(time)))
  tq <- as.numeric(q$time); t <- as.numeric(time)
  i <- findInterval(t, tq)
  before <- pmax(i, 1); after <- pmin(i + 1, length(tq))
  pick <- ifelse(i == 0 | (i < length(tq) & abs(tq[after] - t) < abs(t - tq[before])), after, before)
  ifelse(abs(tq[pick] - t) <= QNH_MAX_GAP_H * 3600, q$qnh_hpa[pick], NA_real_)
}

# Load the daily .Rda files, keeping the samples of the given airports
load_fr24 <- function(fr24_dir, airports, verbose = TRUE) {
  files <- list.files(fr24_dir, pattern = "[.]Rda$", full.names = TRUE)
  if (!length(files)) stop("No .Rda files found in ", fr24_dir)
  if (verbose) cat(sprintf("Found %d daily files\n", length(files)))
  parts <- list()
  for (f in files) {
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
    if (verbose) cat(sprintf("  %s\n", basename(f)))
    rm(d, env); invisible(gc())
  }
  bind_rows(parts)
}

hdiff <- function(a, b) { d <- abs(a - b) %% 360; pmin(d, 360 - d) }

# Steps 1-5 for one airport. Returns list(traj, qc): traj has one row per kept sample with the
# runway (rwy, rwy_head) and alt_msl_m; qc is a one-row tibble of counts.
prepare_tracks <- function(pts, a, icao, qnh = NULL) {
  n_loaded <- nrow(pts)
  pts <- pts %>% distinct(indicat, time, phase, lat, lon, alt, .keep_all = TRUE)
  n_copies <- n_loaded - nrow(pts)
  boundary <- pts %>% distinct(indicat, time, lat, lon, phase) %>% count(indicat, time, lat, lon) %>% filter(n > 1)
  pts <- pts %>% anti_join(boundary, by = c("indicat", "time", "lat", "lon")) %>% arrange(indicat, time)
  arr <- pts %>% filter(flow == "ARR") %>% group_by(indicat) %>%
    mutate(rn = row_number(), z = phase == "GND_ARR" & alt == 0,
           cut = ifelse(any(z), min(which(z)), Inf),
           rwy_head = if (any(z)) head[min(which(z))] else NA_real_) %>%
    filter(phase == "ARR_40" | (phase == "GND_ARR" & rn <= cut)) %>% ungroup()
  dep <- pts %>% filter(flow == "DEP") %>% group_by(indicat) %>%
    mutate(rn = row_number(), z = phase == "GND_DEP" & alt == 0,
           cut = ifelse(any(z), max(which(z)), Inf),
           rwy_head = if (any(z)) head[max(which(z))] else NA_real_) %>%
    filter(phase == "DEP_40" | (phase == "GND_DEP" & rn >= cut)) %>% ungroup()
  n_ground_dropped <- nrow(pts) - nrow(arr) - nrow(dep)
  traj <- bind_rows(arr, dep) %>% filter(!is.na(rwy_head)) %>% select(-rn, -z, -cut)
  q <- if (is.null(qnh)) NULL else qnh %>% filter(station == icao)
  traj$qnh_hpa <- if (is.null(q)) NA_real_ else nearest_qnh(traj$time, q)
  airborne <- traj$alt != 0
  n_qnh_missing <- if (is.null(q)) NA_integer_ else sum(airborne & is.na(traj$qnh_hpa))
  alt_ft <- ifelse(!airborne, a$elev_m / FT,
                   ifelse(is.na(traj$qnh_hpa), traj$alt, pressure_to_qnh_altitude(traj$alt, traj$qnh_hpa)))
  traj <- traj %>% mutate(rwy = ifelse(hdiff(rwy_head, a$axis) <= hdiff(rwy_head, a$axis + 180), a$rwy[1], a$rwy[2]),
                          alt_msl_m = alt_ft * FT)
  low <- airborne & alt_ft < a$elev_m / FT - LOW_LIMIT_FT
  traj <- traj[!low, , drop = FALSE]
  by_rwy <- traj %>% distinct(indicat, rwy) %>% count(rwy)
  n_rwy <- function(r) sum(by_rwy$n[by_rwy$rwy == r])
  qc <- tibble(icao = icao, samples_loaded = n_loaded, exact_copies = n_copies, boundary_points = nrow(boundary),
               ground_samples_trimmed = n_ground_dropped, implausibly_low = sum(low), samples_kept = nrow(traj),
               flights = n_distinct(traj$indicat), rwy_a = a$rwy[1], flights_rwy_a = n_rwy(a$rwy[1]),
               rwy_b = a$rwy[2], flights_rwy_b = n_rwy(a$rwy[2]),
               altitude = if (is.null(q)) "pressure altitude (no QNH table)" else "QNH-corrected",
               qnh_missing = n_qnh_missing,
               qnh_median_hpa = if (is.null(q)) NA_real_ else median(traj$qnh_hpa[traj$alt != 0], na.rm = TRUE))
  list(traj = traj, qc = qc)
}
