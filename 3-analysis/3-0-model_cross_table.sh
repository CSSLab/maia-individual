#!/bin/bash
set -e

max_screens=40

targets_dir="../../data/transfer_players"
outputs_dir="../../data/transfer_results_cross"

models_dir="../../transfer_training/final_models"

target_models=`echo ../../transfer_training/final_models/{no_stop,unfrozen_copy}/*`

mkdir -p $outputs_dir

for model in $target_models; do
    player=`python3 get_models_player.py ${model}`
    model_type=`dirname ${model}`
    model_type=`basename ${model_type}`
    model_name=`basename ${model}`
    echo $player $model_type $model
    for c in "white" "black"; do
        for t in "train" "extended"; do
            player_files=${targets_dir}_${t}/$player/csvs/test_${c}.csv.bz2
            if [ -f "$player_files" ]; then
                player_ret_dir=$outputs_dir/$player
                mkdir -p $player_ret_dir
                echo $player_files
                for model2 in $target_models; do
                    model2_name=`basename ${model2}`
                    model2_player=`python3 get_models_player.py ${model2}`
                    screen -S "cross-${player}-${model2_player}-${c}" -dm bash -c "source ~/.bashrc; python3 prediction_generator.py --target_player ${player} $model2 ${player_files} ${player_ret_dir}/${model2_player}_${c}.csv.bz2"
                done
                while [ `screen -ls | wc -l` -gt $max_screens ]; do
                        printf "waiting\r"
                        sleep 10
                    done
            fi
        done
    done
done
