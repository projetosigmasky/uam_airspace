# Synthetic tracks with known traffic streams, for --stations=stream. Per airport, in the runway
# frame (s along the axis heading, c to its right; NM), every flight uses the axis-heading runway:
#   ARR straight-in  40 flights, final from 10.5 NM out
#   ARR circuit      25 flights, base leg 5.5 NM out, 2-NM-radius turn onto a 3.5-NM final
#   DEP straight-out 30 flights
#   DEP turning      20 flights, 2-NM-radius turn to the left 3 NM out
# Nominal paths run from the runway outwards; each flight is offset from its nominal path by a fixed
# distance along the left normal, 3/4 of the flights spread over -0.05..0.05 NM and 1/4 over
# 0.35..0.45 NM, so the P5-P95 band is off-center and its side is testable. Altitude depends only on
# the distance u along the nominal path: elevation + 318 ft/NM for arrivals (3 degrees), + 600 ft/NM
# for departures. The streams, offsets and profiles are exported as `streams` (sourced by the tests).
STEP <- 0.05
offsets <- function(n) { m <- n - n %/% 4; c(seq(-0.05, 0.05, length.out = m), seq(0.35, 0.45, length.out = n - m)) }
# nominal path from the runway outwards: straight legs and arcs, as (s, c) points every STEP NM
path <- function(legs) {
  p <- c(0, 0); h <- pi; pts <- list(p)          # h: direction in the (s, c) plane, pi = toward -s
  for (L in legs) {
    n <- round(L$len / STEP)
    for (i in seq_len(n)) {
      if (!is.null(L$turn)) h <- h + L$turn * STEP / L$radius
      p <- p + STEP * c(cos(h), sin(h)); pts[[length(pts) + 1]] <- p
    }
  }
  m <- do.call(rbind, pts)
  d <- rbind(m[2, ] - m[1, ], diff(m)); t <- d / sqrt(rowSums(d^2))
  list(s = m[, 1], c = m[, 2], ts = t[, 1], tc = t[, 2], u = (seq_len(nrow(m)) - 1) * STEP)
}
# left normal (geographic sense) of the outward path in the (s, c) frame; c points right of +s
left_normal <- function(p) cbind(p$tc, -p$ts)
streams <- list(
  ARR_straight = list(flow = "ARR", n = 40, rate = 318, legs = list(list(len = 10.5))),
  ARR_circuit  = list(flow = "ARR", n = 25, rate = 318, legs = list(list(len = 3.5), list(len = pi, turn = 1, radius = 2), list(len = 9.5))),
  DEP_straight = list(flow = "DEP", n = 30, rate = 600, legs = list(list(len = 10.5))),
  DEP_turning  = list(flow = "DEP", n = 20, rate = 600, legs = list(list(len = 3), list(len = pi, turn = 1, radius = 2), list(len = 8))))
for (k in names(streams)) streams[[k]]$path <- path(streams[[k]]$legs)
# departures fly the axis heading, i.e. toward +s from the runway: mirror the arrival-style paths
for (k in c("DEP_straight", "DEP_turning")) {
  p <- streams[[k]]$path; p$s <- -p$s; p$ts <- -p$ts; streams[[k]]$path <- p
}
airports_syn <- list(SBSP = list(lat = -23.6261, lon = -46.6564, axis = 147, elev = 2631),
                     SBGR = list(lat = -23.4356, lon = -46.4731, axis = 74, elev = 2461))

make_tracks <- function() {
  rows <- list()
  for (icao in names(airports_syn)) {
    A <- airports_syn[[icao]]; H <- A$axis * pi / 180; id <- 0
    for (k in names(streams)) {
      S <- streams[[k]]; p <- S$path
      n_left <- left_normal(p); ns <- n_left[, 1]; nc <- n_left[, 2]
      for (d in offsets(S$n)) {
        id <- id + 1
        s <- p$s + d * ns; c <- p$c + d * nc
        alt <- A$elev + S$rate * p$u
        e <- s * sin(H) + c * cos(H); n <- s * cos(H) - c * sin(H)
        lat <- A$lat + n / 60; lon <- A$lon + e / (60 * cos(A$lat * pi / 180))
        ord <- if (S$flow == "ARR") rev(seq_along(s)) else seq_along(s)     # time order
        lat <- lat[ord]; lon <- lon[ord]; alt <- alt[ord]; e <- e[ord]; n <- n[ord]
        head <- (atan2(c(diff(e), diff(e)[length(e) - 1]), c(diff(n), diff(n)[length(n) - 1])) * 180 / pi) %% 360
        if (S$flow == "ARR") { alt[length(alt)] <- 0; phase <- c(rep("ARR_40", length(s) - 1), "GND_ARR"); head[length(head)] <- A$axis }
        else { alt[1] <- 0; phase <- c("GND_DEP", rep("DEP_40", length(s) - 1)); head[1] <- A$axis }
        rows[[length(rows) + 1]] <- data.frame(
          indicat = sprintf("%s_%s_%03d", icao, k, id), time = as.POSIXct("2022-12-01", tz = "UTC") + seq_along(s) * 5,
          phase = phase, lat = lat, lon = lon, alt = alt, head = head,
          plan_dep = if (S$flow == "DEP") icao else "XXXX", plan_arr = if (S$flow == "ARR") icao else "XXXX",
          stringsAsFactors = FALSE)
      }
    }
  }
  do.call(rbind, rows)
}

if (sys.nframe() == 0) {
  df <- make_tracks()
  save(df, file = file.path(commandArgs(TRUE)[1], "2022-12-01.Rda"))
  cat("synthetic stream samples:", nrow(df), "\n")
}
