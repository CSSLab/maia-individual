#!/bin/bash
set -e

max_screens=40

targets_dir="../../data/transfer_players"
outputs_dir="../../data/transfer_results"
kdd_path="../../datasets/10000_full_2019-12.csv.bz2"

mkdir -p outputs_dir

maias_dir=../../models/maia

for t in "train" "extended" "validate"; do
    for player_dir in ${targets_dir}_${t}/*; do
        for model in $maias_dir/1{1..9..2}00; do
            maia_type=`basename ${model}`
            player_ret_dir=$outputs_dir/$t/$player/maia
            mkdir -p $player_ret_dir
            player=`basename ${player_dir}`
            echo $t $maia_type $player
            for c in "white" "black"; do
                player_files=${player_dir}/csvs/test_${c}.csv.bz2
                screen -S "baselines-${player}-${maia_type}-${c}" -dm bash -c "source ~/.bashrc; python3 prediction_generator.py --target_player ${player} $model ${player_files} ${player_ret_dir}/${maia_type}_${c}.csv.bz2"
            done
            while [ `screen -ls | wc -l` -gt $max_screens ]; do
                    printf "waiting\r"
                    sleep 10
                done
        done
    done
done

