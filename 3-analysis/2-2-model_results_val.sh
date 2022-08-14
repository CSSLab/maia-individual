#!/bin/bash
set -e

max_screens=50

targets_dir="../../data/transfer_players"
outputs_dir="../../data/transfer_results_val"
summaries_dir="../../data/transfer_summaries"
kdd_path="../../data/reduced_kdd_test_set.csv.bz2"


models_dir="../../transfer_training/final_models_val"
mkdir -p $outputs_dir
mkdir -p $summaries_dir

for model in $models_dir/*/*; do
    player=`python3 get_models_player.py ${model}`
    model_type=`dirname ${model}`
    model_type=`basename ${model_type}`
    model_name=`basename ${model}`
    #echo $model $model_type $model_name $player
    for t in "train" "validate"; do
        for c in "white" "black"; do
            player_files=${targets_dir}_${t}/$player/csvs/test_${c}.csv.bz2
            if [ -f "$player_files" ]; then
                echo $player_files
                player_ret_dir=$outputs_dir/$t/$player/${t}/$model_type
                player_sum_dir=$summaries_dir/$t/$player/${t}/$model_type
                mkdir -p $player_ret_dir
                screen -S "val-tests-${player}-${model_type}-${c}" -dm bash -c "source ~/.bashrc; python3 prediction_generator.py --target_player ${player} $model ${player_files} ${player_ret_dir}/${model_name}_${c}.csv.bz2;python3 make_summary.py ${player_ret_dir}/${model_name}_${c}.csv.bz2 ${player_sum_dir}/${model_name}_${c}.json"
            fi
        done
    done
    screen -S "val-tests-${player}-${model_type}-kdd" -dm bash -c "source ~/.bashrc; python3 prediction_generator.py $model ${kdd_path} ${player_ret_dir}/${model_name}_kdd_reduced.csv.bz2;python3 make_summary.py ${player_ret_dir}/${model_name}_kdd_reduced.csv.bz2
    ${player_sum_dir}/${model_name}_kdd_reduced.csv.bz2"
    while [ `screen -ls | wc -l` -gt $max_screens ]; do
            printf "waiting\r"
            sleep 10
    done
    #screen -S "transfer-tests-${player}-${model_type}-kdd" -dm bash -c  "source ~/.bashrc; python3 prediction_generator.py $model ${kdd_path} ${player_ret_dir}/${model_name}_kdd.csv.bz2"
done


