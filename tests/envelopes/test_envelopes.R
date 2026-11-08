#!/usr/bin/env Rscript
# Tests of generate_approach_surfaces_fr24.R without licensed data. Usage: Rscript tests/envelopes/test_envelopes.R
#   1. The default (radial) output on synthetic tracks (tests/envelopes/make_synthetic_fr24.R: straight-in
#      finals at known lateral offsets after a downwind leg) must match
#      tests/envelopes/expected/synthetic_default_*.csv, and the removed along-axis options must be rejected.
#   2. --stations=stream on synthetic streams (tests/envelopes/make_synthetic_streams.R: straight-in and
#      circuit arrivals, straight-out and turning departures): each stream must be found, follow
#      its known path and climb profile, span its P5-P95 lateral band and be smooth.
#   3. Track quality control (tools/fr24_tracks.R) on a small synthetic sample set with each known
#      defect (taxi samples before lift-off, a phase-boundary point with an interpolated low
#      altitude, an exact copy, ground samples after touchdown, an implausibly low sample), the
#      pressure-to-QNH altitude conversion and the METAR matching; and --qnh end to end (a constant
#      1013.25-hPa table must reproduce the reference outputs).
# Requires R with dplyr. Exit status 0 when every check passes.
script_arg <- grep("^--file=", commandArgs(FALSE), value = TRUE)
here <- if (length(script_arg)) dirname(normalizePath(sub("^--file=", "", script_arg))) else file.path("tests", "envelopes")
root <- normalizePath(file.path(here, "..", ".."))
generator <- file.path(root, "tools", "generate_approach_surfaces_fr24.R")
results <- logical()
check <- function(name, ok, detail = "") {
  results[[length(results) + 1]] <<- isTRUE(ok)
  cat(sprintf("  %s  %s%s\n", if (isTRUE(ok)) "PASS" else "FAIL", name, if (nzchar(detail)) paste0("  (", detail, ")") else ""))
}

# ---------------------------------------------------------------- 1. radial envelopes
cat("Radial envelopes (tests/envelopes/make_synthetic_fr24.R)
")
FT <- 0.3048
rscript <- file.path(R.home("bin"), "Rscript")
tmp <- tempfile("envelope-test-"); dir.create(file.path(tmp, "in"), recursive = TRUE); dir.create(file.path(tmp, "out"))
run <- function(...) suppressWarnings(system2(rscript, c(...), stdout = TRUE, stderr = TRUE))
invisible(run(shQuote(file.path(here, "make_synthetic_fr24.R")), shQuote(file.path(tmp, "in"))))
invisible(run(shQuote(generator), shQuote(file.path(tmp, "in")), shQuote(file.path(tmp, "out"))))
out <- function(name) file.path(tmp, "out", name)
expected <- file.path(here, "expected")
for (f in c("approach_surfaces_SBGR.csv", "approach_surfaces_SBSP.csv", "approach_surfaces_stations.csv", "approach_surfaces_summary.csv")) {
  a <- read.csv(out(f)); b <- read.csv(file.path(expected, paste0("synthetic_default_", f)))
  same <- identical(names(a), names(b)) && nrow(a) == nrow(b) &&
    all(mapply(function(u, v) if (is.numeric(u)) isTRUE(all.equal(u, v, tolerance = 1e-9)) else identical(as.character(u), as.character(v)), a, b))
  check(sprintf("default (radial) output %s matches tests/envelopes/expected", f), same)
}
for (opt in list("--stations=axis", c("--lateral=traffic", "--align=30"))) {
  r <- run(shQuote(generator), shQuote(file.path(tmp, "in")), shQuote(file.path(tmp, "out")), opt)
  check(sprintf("removed along-axis option rejected (%s)", paste(opt, collapse = " ")),
        !is.null(attr(r, "status")) && attr(r, "status") != 0 && !length(list.files(file.path(tmp, "out"), "axis|align")))
}

# ---------------------------------------------------------------- 2. stream envelopes
cat("Stream envelopes (tests/envelopes/make_synthetic_streams.R)\n")
syn <- new.env(); sys.source(file.path(here, "make_synthetic_streams.R"), envir = syn)
dir.create(file.path(tmp, "in_streams")); dir.create(file.path(tmp, "out_streams"))
invisible(run(shQuote(file.path(here, "make_synthetic_streams.R")), shQuote(file.path(tmp, "in_streams"))))
invisible(run(shQuote(generator), shQuote(file.path(tmp, "in_streams")), shQuote(file.path(tmp, "out_streams")), "--stations=stream"))
sout <- function(name) file.path(tmp, "out_streams", name)
check("stream outputs written with the _stream suffix",
      all(file.exists(sout(c("approach_surfaces_SBSP_stream.csv", "approach_surfaces_SBGR_stream.csv",
                             "approach_surfaces_stations_stream.csv", "approach_surfaces_summary_stream.csv")))))
summ <- read.csv(sout("approach_surfaces_summary_stream.csv"), colClasses = c(runway = "character"))
sst <- read.csv(sout("approach_surfaces_stations_stream.csv"), colClasses = c(runway = "character"))
truth_of <- c(ARR_S1 = "ARR_straight", ARR_S2 = "ARR_circuit", DEP_S1 = "DEP_straight", DEP_S2 = "DEP_turning")
for (icao in names(syn$airports_syn)) {
  A <- syn$airports_syn[[icao]]; H <- A$axis * pi / 180; rwy <- if (icao == "SBSP") "17" else "10"
  sm <- summ[summ$icao == icao, ]
  check(sprintf("%s: two arrival and two departure streams, each flight in its own stream", icao),
        identical(sm$stream, paste0(rep(c("ARR", "DEP"), each = 2), rwy, "_S", 1:2)) && identical(sm$flights, c(40L, 25L, 30L, 20L)),
        paste(sm$stream, sm$flights, collapse = ", "))
  for (nm in sm$stream) {
    S <- syn$streams[[truth_of[[paste0(substr(nm, 1, 3), "_", sub(".*_", "", nm))]]]]; p <- S$path; L <- syn$left_normal(p)
    g <- sst[sst$icao == icao & sst$stream == nm, ]
    e <- (g$lon - A$lon) * cos(A$lat * pi / 180) * 60; n <- (g$lat - A$lat) * 60
    s <- e * sin(H) + n * cos(H); c <- e * cos(H) - n * sin(H)
    j <- sapply(seq_along(s), function(i) which.min((p$s - s[i])^2 + (p$c - c[i])^2))
    offset <- (s - p$s[j]) * L[j, 1] + (c - p$c[j]) * L[j, 2]     # signed, left of the outward path
    q <- quantile(syn$offsets(S$n), c(0.05, 0.95), names = FALSE)
    # stations more than the smoothing length (1 NM) before the first one some flights have left
    short <- which(g$n_flights < S$n)
    inner <- if (length(short)) g$distance_along_path_nm < min(g$distance_along_path_nm[short]) - 1 else rep(TRUE, nrow(g))
    alt_err <- max(abs(c(g$lower_limit_m[inner], g$upper_limit_m[inner]) / FT - rep(A$elev + S$rate * p$u[j][inner], 2)))
    check(sprintf("%s %s follows the known path and climb profile (%s)", icao, nm, truth_of[[paste0(substr(nm, 1, 3), "_", sub(".*_", "", nm))]]),
          sum(inner) >= 80 && alt_err < 50 && max(abs(offset[inner] - mean(q))) < 0.03,
          sprintf("%d stations, altitude error %.1f ft, center %.3f-%.3f NM (P5-P95 mid-point %.3f)",
                  sum(inner), alt_err, min(offset[inner]), max(offset[inner]), mean(q)))
    check(sprintf("%s %s spans the P5-P95 lateral band", icao, nm), max(abs(g$width_nm[inner] - diff(q))) < 0.02,
          sprintf("width %.3f-%.3f NM, expected %.3f", min(g$width_nm[inner]), max(g$width_nm[inner]), diff(q)))
    heading <- atan2(diff(c), diff(s)); turn <- abs(((diff(heading) + pi) %% (2 * pi)) - pi) * 180 / pi
    check(sprintf("%s %s is smooth (heading change < 6 deg and width ratio < 1.2 between stations)", icao, nm),
          max(turn) < 6 && max(exp(abs(diff(log(g$width_nm[inner]))))) < 1.2, sprintf("max heading change %.1f deg", max(turn)))
  }
}
routes <- read.csv(sout("approach_surfaces_SBSP_stream.csv"))
check("stream route file: one route per stream, ids from the runway outwards",
      identical(unique(routes$route), c("ARR17_S1", "ARR17_S2", "DEP17_S1", "DEP17_S2")) &&
        all(tapply(routes$id, routes$route, function(i) identical(i, seq_along(i)))))

# ---------------------------------------------------------------- 3. track quality control
cat("Track quality control (tools/fr24_tracks.R)\n")
qc_env <- new.env(); sys.source(file.path(root, "tools", "fr24_tracks.R"), envir = qc_env)
suppressMessages(library(dplyr))
a <- list(lat = -23.4356, lon = -46.4731, axis = 74, elev_m = 2461 * FT, rwy = c(10, 28))
t0 <- as.POSIXct("2022-12-01 12:00:00", tz = "UTC")
pt <- function(id, sec, phase, x_nm, alt, flow, head = 74)
  data.frame(icao = "SBGR", indicat = id, time = t0 + sec, phase = phase, lat = a$lat, lon = a$lon + x_nm / (60 * cos(a$lat * pi / 180)),
             alt = alt, head = head, flow = flow, stringsAsFactors = FALSE)
pts <- rbind(
  # departure 1: taxi (zeros) far from the runway end, lift-off zero, boundary point at 1 NM (both phases), climb
  pt(1, 0, "GND_DEP", -0.5, 0, "DEP", 160), pt(1, 30, "GND_DEP", -0.6, 0, "DEP", 160), pt(1, 60, "GND_DEP", -0.4, 0, "DEP", 74),
  pt(1, 90, "GND_DEP", 0.9, 0, "DEP"), pt(1, 93, "GND_DEP", 1.0, 821.2, "DEP"), pt(1, 93, "DEP_40", 1.0, 821.2, "DEP"),
  pt(1, 98, "DEP_40", 1.3, 2700, "DEP"), pt(1, 104, "DEP_40", 1.7, 3000, "DEP"), pt(1, 104, "DEP_40", 1.7, 3000, "DEP"),
  # arrival 2: approach, boundary point, touchdown zero, roll-out zeros
  pt(2, 0, "ARR_40", -3, 3200, "ARR"), pt(2, 40, "ARR_40", -1.5, 2700, "ARR"), pt(2, 60, "GND_ARR", -1, 2500.5, "ARR"),
  pt(2, 60, "ARR_40", -1, 2500.5, "ARR"), pt(2, 70, "GND_ARR", -0.5, 0, "ARR"), pt(2, 80, "GND_ARR", 0, 0, "ARR"),
  # departure 3: one airborne sample 1,000 ft below the field elevation
  pt(3, 0, "GND_DEP", 0.5, 0, "DEP"), pt(3, 10, "DEP_40", 1.5, 1461, "DEP"), pt(3, 20, "DEP_40", 2.5, 3100, "DEP"))
res <- qc_env$prepare_tracks(pts, a, "SBGR")
q <- res$qc; tr <- res$traj
check("exact copies kept once", q$exact_copies == 1, sprintf("%d", q$exact_copies))
check("phase-boundary points removed (both copies)", q$boundary_points == 2 && !any(tr$alt %in% c(821.2, 2500.5)), sprintf("%d points", q$boundary_points))
check("departure starts at the lift-off zero (taxi samples trimmed)",
      isTRUE(all.equal(as.numeric(tr$time[tr$indicat == 1 & tr$alt == 0]), as.numeric(t0 + 90))) && sum(tr$indicat == 1) == 3)
check("arrival ends at the touchdown zero (roll-out trimmed)", as.numeric(max(tr$time[tr$indicat == 2])) == as.numeric(t0 + 70))
check("ground trimming counted", q$ground_samples_trimmed == 4, sprintf("%d", q$ground_samples_trimmed))
check("implausibly low airborne sample removed", q$implausibly_low == 1 && !any(tr$alt == 1461), sprintf("%d", q$implausibly_low))
check("without a QNH table, altitudes are pressure altitudes; ground zeros take the field elevation",
      all(abs(tr$alt_msl_m[tr$alt > 0] - tr$alt[tr$alt > 0] * FT) < 1e-9) && all(tr$alt_msl_m[tr$alt == 0] == a$elev_m))
p2q <- qc_env$pressure_to_qnh_altitude
check("QNH 1013.25 hPa leaves pressure altitudes unchanged", max(abs(p2q(c(0, 2461, 5000), 1013.25) - c(0, 2461, 5000))) < 1e-6)
grad <- (p2q(2461, 1016) - p2q(2461, 1014)) / 2
check("near the field, 1 hPa of QNH is about 27 ft", grad > 26 && grad < 29, sprintf("%.1f ft/hPa", grad))
qtab <- data.frame(station = "SBGR", time = t0 + c(-3600, 0, 3600), qnh_hpa = c(1010, 1020, 1015))
check("nearest METAR in time, none beyond 3 h",
      identical(qc_env$nearest_qnh(t0 + c(-3000, 100, 2000, 4 * 3600 + 1), qtab), c(1010, 1020, 1015, NA)))
resq <- qc_env$prepare_tracks(pts, a, "SBGR", qnh = qtab)
x <- resq$traj %>% filter(indicat == 1, alt == 2700)
check("with a QNH table, airborne altitudes are QNH altitudes", abs(x$alt_msl_m / FT - p2q(2700, 1020)) < 1e-6,
      sprintf("2,700 ft pressure altitude -> %.0f ft at QNH 1020", x$alt_msl_m / FT))
# --qnh end to end: a constant 1013.25-hPa table must reproduce the reference outputs
qfile <- file.path(tmp, "qnh_standard.csv")
write.csv(data.frame(station = rep(c("SBGR", "SBSP"), each = 3), valid_utc = rep(c("2022-12-01 00:00", "2022-12-01 01:00", "2022-12-01 02:00"), 2),
                     qnh_hpa = 1013.25), qfile, row.names = FALSE)
dir.create(file.path(tmp, "out_qnh"))
invisible(run(shQuote(generator), shQuote(file.path(tmp, "in")), shQuote(file.path(tmp, "out_qnh")), paste0("--qnh=", shQuote(qfile))))
same_all <- all(sapply(c("approach_surfaces_SBGR.csv", "approach_surfaces_SBSP.csv", "approach_surfaces_stations.csv"), function(f) {
  u <- read.csv(file.path(tmp, "out_qnh", f)); v <- read.csv(file.path(expected, paste0("synthetic_default_", f)))
  identical(names(u), names(v)) && nrow(u) == nrow(v) && all(mapply(function(p, r) if (is.numeric(p)) isTRUE(all.equal(p, r, tolerance = 1e-9)) else identical(as.character(p), as.character(r)), u, v))
}))
qc_out <- read.csv(file.path(tmp, "out_qnh", "approach_surfaces_qc.csv"))
check("--qnh with a constant 1013.25-hPa table reproduces the reference outputs and reports QNH correction",
      same_all && all(qc_out$altitude == "QNH-corrected") && all(qc_out$qnh_missing == 0))
unlink(tmp, recursive = TRUE)
cat(sprintf("\n%d passed, %d failed\n", sum(results), sum(!results)))
quit(status = if (all(results)) 0 else 1)
