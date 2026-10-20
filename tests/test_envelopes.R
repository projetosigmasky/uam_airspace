#!/usr/bin/env Rscript
# Tests of generate_approach_surfaces_fr24.R without licensed data. Usage: Rscript tests/test_envelopes.R
#   1. smooth_traffic_lateral() on lateral-percentile profiles that make independently smoothed
#      P5/P95 curves cross: the band must stay finite, positive, ordered and close to the raw width.
#   2. The script end to end on synthetic tracks (tests/make_synthetic_fr24.R): the along-axis,
#      traffic-centred, heading-aligned envelope must recover the known 3-degree profile, and the
#      default (radial) output must match tests/expected/synthetic_default_*.csv.
#   3. --stations=stream on synthetic streams (tests/make_synthetic_streams.R: straight-in and
#      circuit arrivals, straight-out and turning departures): each stream must be found, follow
#      its known path and climb profile, span its P5-P95 lateral band and be smooth.
# Requires R with dplyr. Exit status 0 when every check passes.
script_arg <- grep("^--file=", commandArgs(FALSE), value = TRUE)
here <- if (length(script_arg)) dirname(normalizePath(sub("^--file=", "", script_arg))) else "tests"
root <- normalizePath(file.path(here, ".."))
generator <- file.path(root, "generate_approach_surfaces_fr24.R")
results <- logical()
check <- function(name, ok, detail = "") {
  results[[length(results) + 1]] <<- isTRUE(ok)
  cat(sprintf("  %s  %s%s\n", if (isTRUE(ok)) "PASS" else "FAIL", name, if (nzchar(detail)) paste0("  (", detail, ")") else ""))
}

# ---------------------------------------------------------------- 1. lateral smoothing
# take the function definitions from the script itself (without running it)
fun_env <- new.env()
for (e in parse(generator)) {
  if (is.call(e) && identical(e[[1]], as.name("<-")) && is.name(e[[2]]) &&
      as.character(e[[2]]) %in% c("SMOOTHING_SPL", "MIN_WIDTH_NM", "LOCAL_RANGE_NM", "smooth_col", "smooth_traffic_lateral")) eval(e, fun_env)
}
smooth_col <- fun_env$smooth_col
smooth_traffic_lateral <- fun_env$smooth_traffic_lateral
cat("Lateral smoothing (smooth_traffic_lateral)\n")
x <- seq(0, 10, by = 0.1)
# a narrow band (0.07 NM) that widens gradually, then a second stream 8 NM to one side from 8.7 NM,
# as on the SBGR runway 28 side in December 2022
c5 <- -0.02 - 0.01 * pmax(0, x - 7)
c95 <- ifelse(x < 8.65, 0.05 + 0.01 * pmax(0, x - 7), 8.3)
indep <- smooth_col(x, c95) - smooth_col(x, c5)
check("the test profile makes independently smoothed P5/P95 curves cross", any(indep <= 0),
      sprintf("%d crossed stations", sum(indep <= 0)))
r <- smooth_traffic_lateral(x, c5, c95)
raw <- c95 - c5
check("smoothed band is finite and strictly positive", all(is.finite(r$centre)) && all(is.finite(r$width)) && all(r$width > 0))
lo <- r$centre - r$width / 2; hi <- r$centre + r$width / 2
check("lower limit below upper limit everywhere", all(lo < hi))
check("the band contains each station's raw P5-P95 band", all(lo <= c5 + 1e-12) && all(hi >= c95 - 1e-12))
near <- lapply(x, function(xi) abs(x - xi) <= 1.0 + 1e-9)
check("no edge beyond the outermost raw edges within 1 NM (no overshoot at the step)",
      all(mapply(function(l, h, k) l >= min(c5[k]) - 1e-12 && h <= max(c95[k]) + 1e-12, lo, hi, near)),
      sprintf("width %.3f-%.3f NM for raw %.3f-%.3f NM", min(r$width), max(r$width), min(raw), max(raw)))
# the spline (spar = 0.5, 0.1-NM stations) spreads a step over about +/-1 NM, as for the altitudes
rc <- (c5 + c95) / 2
away <- abs(x - 8.65) > 1.0
excess <- pmax(c5 - lo, hi - c95)
check("more than 1 NM from the step, the band exceeds the raw band by less than half a 50-m cell on each side",
      max(excess[away]) < 25 / 1852, sprintf("max %.4f NM = %.1f m; width/raw %.3f-%.3f", max(excess[away]), 1852 * max(excess[away]),
                                             min(r$width[away] / raw[away]), max(r$width[away] / raw[away])))
check("no station collapses to the numerical guard", min(r$width) > 10 * fun_env$MIN_WIDTH_NM, sprintf("min %.4f NM", min(r$width)))
jump <- diff(range(rc))
check("more than 1 NM from the step, centre within 2% of the centre jump", max(abs(r$centre[away] - rc[away])) < 0.02 * jump,
      sprintf("max offset %.4f NM for a %.2f-NM jump", max(abs(r$centre[away] - rc[away])), jump))
err_at <- sapply(c(0.6, 1.0, 1.5, 2.0), function(d) max(abs(r$centre[abs(x - 8.65) > d] - rc[abs(x - 8.65) > d])))
check("centre error does not grow with distance from the step (no ringing)", all(diff(err_at) <= 1e-12), paste(sprintf("%.4f", err_at), collapse = " > "))
check("deterministic", identical(r, smooth_traffic_lateral(x, c5, c95)))
narrow <- smooth_traffic_lateral(x, rep(-0.01, length(x)), rep(0.01, length(x)))
check("a constant narrow band (0.02 NM) is kept exactly", max(abs(narrow$width - 0.02)) < 1e-9 && max(abs(narrow$centre)) < 1e-9)
z <- smooth_traffic_lateral(x, c(rep(0, 5), c5[-(1:5)]), c(rep(0, 5), c95[-(1:5)]))
check("zero raw widths are counted and handled", z$floored == 5 && all(is.finite(z$width)) && all(z$width > 0), sprintf("%d floored", z$floored))
check("inverted raw percentiles are rejected", inherits(try(smooth_traffic_lateral(x, c95, c5), silent = TRUE), "try-error"))

# ---------------------------------------------------------------- 2. synthetic tracks end to end
cat("Synthetic tracks (tests/make_synthetic_fr24.R)\n")
rscript <- file.path(R.home("bin"), "Rscript")
tmp <- tempfile("envelope-test-"); dir.create(file.path(tmp, "in"), recursive = TRUE); dir.create(file.path(tmp, "out"))
run <- function(...) system2(rscript, c(...), stdout = TRUE, stderr = TRUE)
invisible(run(shQuote(file.path(here, "make_synthetic_fr24.R")), shQuote(file.path(tmp, "in"))))
invisible(run(shQuote(generator), shQuote(file.path(tmp, "in")), shQuote(file.path(tmp, "out"))))
invisible(run(shQuote(generator), shQuote(file.path(tmp, "in")), shQuote(file.path(tmp, "out")),
              "--stations=axis", "--lateral=traffic", "--align=30"))
out <- function(name) file.path(tmp, "out", name)
check("default and along-axis outputs written with distinct names",
      all(file.exists(out(c("approach_surfaces_SBSP.csv", "approach_surfaces_stations.csv",
                            "approach_surfaces_SBSP_axis_traffic_align30.csv", "approach_surfaces_stations_axis_traffic_align30.csv")))))
st <- read.csv(out("approach_surfaces_stations_axis_traffic_align30.csv"))
FT <- 0.3048
for (side in list(c("SBSP", "SIDE_35", 2631), c("SBGR", "SIDE_28", 2461))) {
  g <- st[st$icao == side[1] & st$side == side[2], ]
  at <- sapply(c(1, 3, 5, 8), function(d) which.min(abs(g$distance_nm - d)))
  truth <- as.numeric(side[3]) + 318 * g$distance_nm[at]
  err <- max(abs(c(g$lower_limit_m[at], g$upper_limit_m[at]) / FT - rep(truth, 2)))
  check(sprintf("%s %s along-axis envelope recovers the 3-degree profile (1, 3, 5, 8 NM)", side[1], side[2]), err < 50,
        sprintf("max error %.1f ft", err))
  check(sprintf("%s %s along-axis band centred on the traffic, 2 NM wide", side[1], side[2]),
        max(abs(abs(g$centre_offset_nm[at]) - 2)) < 0.1 && max(abs(g$width_nm[at] - 2)) < 0.1,
        sprintf("centre %.2f, width %.2f NM", mean(abs(g$centre_offset_nm[at])), mean(g$width_nm[at])))
}
check("no along-axis station at the numerical width guard", all(st$width_nm > 2 * fun_env$MIN_WIDTH_NM), sprintf("min %.4f NM", min(st$width_nm)))
expected <- file.path(here, "expected")
for (f in c("approach_surfaces_SBGR.csv", "approach_surfaces_SBSP.csv", "approach_surfaces_stations.csv", "approach_surfaces_summary.csv")) {
  a <- read.csv(out(f)); b <- read.csv(file.path(expected, paste0("synthetic_default_", f)))
  same <- identical(names(a), names(b)) && nrow(a) == nrow(b) &&
    all(mapply(function(u, v) if (is.numeric(u)) isTRUE(all.equal(u, v, tolerance = 1e-9)) else identical(as.character(u), as.character(v)), a, b))
  check(sprintf("default (radial) output %s matches tests/expected", f), same)
}

# ---------------------------------------------------------------- 3. stream envelopes
cat("Stream envelopes (tests/make_synthetic_streams.R)\n")
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
          sprintf("%d stations, altitude error %.1f ft, centre %.3f-%.3f NM (P5-P95 mid-point %.3f)",
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
unlink(tmp, recursive = TRUE)
cat(sprintf("\n%d passed, %d failed\n", sum(results), sum(!results)))
quit(status = if (all(results)) 0 else 1)
