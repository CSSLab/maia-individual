#!/bin/bash

data_dir="/maiadata/transfer_players_train"

for player_dir in $data_dir/*; do
    player_name=`basename ${player_dir}`
    mkdir $player_dir/csvs
    for c in "white" "black"; do
        for s in "train" "validate" "test"; do
            target=$player_dir/split/${s}_${c}.pgn.bz2
            output=$player_dir/csvs/${s}_${c}.csv.bz2
            echo ${player_name} ${s} ${c}
            screen -S "csv-${player_name}-${c}-${s}" -dm bash -c "python3 ../../data_generators/pgn_to_csv.py ${target} ${output}"
        done
    done
done
