#!/bin/bash
set -e

max_screens=50

targets_dir="../../data/transfer_players"
outputs_dir="../../data/transfer_results"
kdd_path="../../datasets/10000_full_2019-12.csv.bz2"


models_dir="../../transfer_training/final_models"
mkdir -p outputs_dir

for model in $models_dir/*/*; do
    player=`python3 get_models_player.py ${model}`
    model_type=`dirname ${model}`
    model_type=`basename ${model_type}`
    model_name=`basename ${model}`
    #echo $model $model_type $model_name $player

    for c in "white" "black"; do
        for t in "train" "extended"; do
            player_files=${targets_dir}_${t}/$player/csvs/test_${c}.csv.bz2
            if [ -f "$player_files" ]; then
                echo $player_files
                player_ret_dir=$outputs_dir/$t/$player/transfer/$model_type
                mkdir -p $player_ret_dir
                screen -S "transfer-tests-${player}-${model_type}-${c}" -dm bash -c "source ~/.bashrc; python3 prediction_generator.py --target_player ${player} $model ${player_files} ${player_ret_dir}/${model_name}_${c}.csv.bz2"
            fi
        done
    done
    while [ `screen -ls | wc -l` -gt $max_screens ]; do
            printf "waiting\r"
            sleep 10
    done
    #screen -S "transfer-tests-${player}-${model_type}-kdd" -dm bash -c  "source ~/.bashrc; python3 prediction_generator.py $model ${kdd_path} ${player_ret_dir}/${model_name}_kdd.csv.bz2"
done


