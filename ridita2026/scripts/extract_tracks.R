# Extract the SBGR/SBSP arrival and departure track samples exactly as tools/generate_approach_surfaces_fr24.R
# selects them (same filters and ground trimming), for a local traffic-occupancy check.
# Output stays local (licensed Flightradar24 data): tracks.csv.gz with indicat, icao, flow, time, lat, lon, alt_msl_m.
suppressMessages(library(dplyr))
args <- commandArgs(TRUE); FR24_DIR <- args[1]; OUT <- args[2]
FT <- 0.3048
airports <- list(SBGR = list(lat = -23.4356, lon = -46.4731, elev_m = 2461 * FT),
                 SBSP = list(lat = -23.6261, lon = -46.6564, elev_m = 2631 * FT))
parts <- list()
for (f in list.files(FR24_DIR, pattern = "[.]Rda$", full.names = TRUE)) {
  env <- new.env(); load(f, envir = env); d <- get("df", envir = env)
  for (icao in names(airports)) {
    a <- airports[[icao]]
    parts[[length(parts) + 1]] <- d %>%
      filter(abs(lat - a$lat) < 0.3, abs(lon - a$lon) < 0.3,
             (plan_arr == icao & phase %in% c("ARR_40", "GND_ARR")) | (plan_dep == icao & phase %in% c("DEP_40", "GND_DEP"))) %>%
      transmute(icao = icao, indicat, time, phase, lat, lon, alt, head,
                flow = ifelse(plan_arr == icao & phase %in% c("ARR_40", "GND_ARR"), "ARR", "DEP"))
  }
  rm(d, env); invisible(gc())
}
pts <- bind_rows(parts) %>% arrange(icao, indicat, time)
out <- list()
for (icao in names(airports)) {
  a <- airports[[icao]]
  p <- pts %>% filter(icao == !!icao)
  arr <- p %>% filter(flow == "ARR") %>% group_by(indicat) %>%
    mutate(rn = row_number(), z = phase == "GND_ARR" & alt == 0, first_z = ifelse(any(z), min(which(z)), Inf),
           ok = any(z)) %>% filter(ok, phase == "ARR_40" | (phase == "GND_ARR" & rn <= first_z)) %>% ungroup()
  dep <- p %>% filter(flow == "DEP") %>% group_by(indicat) %>%
    mutate(rn = row_number(), z = phase == "GND_DEP" & alt == 0, first_z = ifelse(any(z), min(which(z)), Inf),
           ok = any(z)) %>% filter(ok, phase == "DEP_40" | (phase == "GND_DEP" & rn >= first_z)) %>% ungroup()
  out[[icao]] <- bind_rows(arr, dep) %>% transmute(indicat, icao, flow, time = as.numeric(time), lat, lon,
                                                   alt_msl_m = ifelse(alt == 0, a$elev_m, alt * FT))
}
res <- bind_rows(out)
cat(sprintf("%s: %d flights, %d samples\n", names(out), sapply(out, function(x) n_distinct(x$indicat)), sapply(out, nrow)), sep = "")
write.csv(res, gzfile(OUT), row.names = FALSE)
cat("Done.\n")
