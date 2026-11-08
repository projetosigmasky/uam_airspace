# Extract the SBGR/SBSP arrival and departure track samples exactly as tools/generate_approach_surfaces_fr24.R
# selects them (shared code in tools/fr24_tracks.R: quality control, ground trimming, altitudes), for a
# local traffic-occupancy check.
# Usage: Rscript extract_tracks.R <folder with the daily .Rda files> <tracks.csv.gz> [--qnh=<METAR QNH table>]
#        (the paper's counts use --qnh=data/envelopes/metar_qnh_2022-12.csv)
# Output stays local (licensed Flightradar24 data): tracks.csv.gz with indicat, icao, flow, time, lat, lon, alt_msl_m.
suppressMessages(library(dplyr))
all_args <- commandArgs(TRUE)
args <- all_args[!grepl("^--", all_args)]; FR24_DIR <- args[1]; OUT <- args[2]
qnh_arg <- grep("^--qnh=", all_args, value = TRUE)
script_arg <- grep("^--file=", commandArgs(FALSE), value = TRUE)
script_dir <- if (length(script_arg)) dirname(normalizePath(sub("^--file=", "", script_arg))) else getwd()
source(file.path(script_dir, "..", "..", "tools", "fr24_tracks.R"))
QNH <- if (length(qnh_arg)) read_qnh(sub("^--qnh=", "", qnh_arg[length(qnh_arg)])) else NULL
airports <- list(SBGR = list(lat = -23.4356, lon = -46.4731, axis = 74, elev_m = 2461 * FT, rwy = c(10, 28)),
                 SBSP = list(lat = -23.6261, lon = -46.6564, axis = 147, elev_m = 2631 * FT, rwy = c(17, 35)))
pts <- load_fr24(FR24_DIR, airports, verbose = FALSE)
out <- list(); qc <- list()
for (icao in names(airports)) {
  prep <- prepare_tracks(pts %>% filter(icao == !!icao), airports[[icao]], icao, QNH)
  out[[icao]] <- prep$traj %>% transmute(indicat, icao, flow, time = as.numeric(time), lat, lon, alt_msl_m)
  qc[[icao]] <- prep$qc
}
print(as.data.frame(bind_rows(qc)))
write.csv(bind_rows(out), gzfile(OUT), row.names = FALSE)
cat("Done.\n")
