#!/bin/bash

targets_dir="../../data/transfer_players_train"
outputs_dir="../../data/transfer_results/train"

maias="../../models/maia"
stockfish="../../models/stockfish/stockfish_d15"
leela="../../models/leela/sergio"


mkdir -p outputs_dir

for player_dir in $targets_dir/*; do
    player=`basename ${player_dir}`
    player_ret_dir=$outputs_dir/$player

    echo $player_dir

    mkdir -p $player_ret_dir
    mkdir -p $player_ret_dir/maia
    mkdir -p $player_ret_dir/leela
    #mkdir -p $player_ret_dir/stockfish
    for c in "white" "black"; do
        player_files=$player_dir/csvs/test_${c}.csv.bz2
        #screen -S "baseline-tests-${player}-leela-${c}" -dm bash -c "source ~/.bashrc; python3 prediction_generator.py --target_player ${player} $leela ${player_files} ${player_ret_dir}/leela/segio_${c}.csv.bz2"
        for maia_path in $maias/*; do
        maia_name=`basename ${maia_path}`
        printf "$maia_name\r"
        screen -S "baseline-tests-${player}-${maia_name}-${c}" -dm bash -c "source ~/.bashrc; python3 prediction_generator.py --target_player ${player} $maia_path ${player_files} ${player_ret_dir}/maia/${maia_name}_${c}.csv.bz2"
        done
    done
done
