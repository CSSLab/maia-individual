##!/bin/bash

lichesss_raw_dir='/data/chess/bz2/standard/'
output_dir='../../data/player_counts'
mkdir -p $output_dir

for t in $lichesss_raw_dir/*-{01..11}.pgn.bz2 $lichesss_raw_dir/*{3..8}-12.pgn.bz2; do
    fname="$(basename -- $t)"
    echo "${t} ${output_dir}/${fname}.csv.bz2"
    screen -S "filter-${fname}" -dm bash -c "source ~/.bashrc; python3 find_top_players.py  ${t} ${output_dir}/${fname}.csv.bz2"
done
