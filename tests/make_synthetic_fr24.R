# Synthetic arrivals with a downwind leg: each flight first flies downwind 5 NM abeam the axis at
# 5,000 ft with the opposite heading (s from 0 to -10.5 NM), then a straight-in final parallel to
# the axis at a known lateral offset (1 or 3 NM) on a 3-degree path (318 ft/NM above field
# elevation), ending with a ground sample abeam the threshold. Truth at along-axis distance d on
# final: elev + 318 d ft. Used for the radial reference outputs in tests/expected/.
set.seed(1)
make <- function(icao, lat0, lon0, axis_deg, elev_ft, offsets, nflights) {
  H <- axis_deg * pi / 180; rows <- list(); id <- 0
  for (c0 in offsets) for (k in seq_len(nflights)) {
    id <- id + 1
    s_dw <- seq(0, -10.5, by = -0.05); s_fin <- seq(-10.5, 0, by = 0.05)
    s <- c(s_dw, s_fin); c <- c(rep(c0 + 4, length(s_dw)), rep(c0, length(s_fin)))
    alt <- c(rep(5000, length(s_dw)), elev_ft + 318 * abs(s_fin)); alt[length(alt)] <- 0
    head <- c(rep((axis_deg + 180) %% 360, length(s_dw)), rep(axis_deg, length(s_fin)))
    e <- s * sin(H) + c * cos(H); n <- s * cos(H) - c * sin(H)
    rows[[length(rows) + 1]] <- data.frame(
      indicat = sprintf("%s_%03d", icao, id), time = as.POSIXct("2022-12-01", tz = "UTC") + seq_along(s) * 5,
      phase = c(rep("ARR_40", length(s) - 1), "GND_ARR"), lat = lat0 + n / 60,
      lon = lon0 + e / (60 * cos(lat0 * pi / 180)), alt = alt, head = head,
      plan_dep = "XXXX", plan_arr = icao, stringsAsFactors = FALSE)
  }
  do.call(rbind, rows)
}
df <- rbind(make("SBSP", -23.6261, -46.6564, 147, 2631, c(1, 3), 10),
            make("SBGR", -23.4356, -46.4731, 74, 2461, c(1, 3), 10))
save(df, file = file.path(commandArgs(TRUE)[1], "2022-12-01.Rda"))
cat("synthetic samples:", nrow(df), "\n")
