#!/bin/bash
set -e

max_screens=40

targets_dir="../../data/transfer_players_validate"
outputs_dir="../../data/transfer_players_validate_cross_csvs"

mkdir -p $outputs_dir

for player_dir in $targets_dir/*; do
    player=`basename ${player_dir}`
    echo $player
    mkdir -p ${outputs_dir}/${player}
    for c in "white" "black"; do
        screen -S "cross-${player}-${c}" -dm bash -c "sourcer ~/.basrc; python3 csv_trimmer.py ${player_dir}/csvs/test_${c}.csv.bz2 ${outputs_dir}/${player}/test_${c}_reduced.csv.bz2"
    done
done

