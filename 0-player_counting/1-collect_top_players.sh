##!/bin/bash

lichesss_raw_dir='/data/chess/bz2/standard/'
counts_dir='../../data/player_counts'
counts_file='../../data/player_counts_combined.csv.bz2'
top_list='../../data/player_counts_combined_top_names.csv.bz2'

output_2000_dir='../../data/top_2000_player_games'
output_2000_metadata_dir='../../data/top_2000_player_data'

players_list='../../data/select_transfer_players'

final_data_dir='../../data/transfer_players_data'

num_train=10
num_val=900
num_test=100

python3 combine_player_counts.py $counts_dir/* $counts_file

bzcat $counts_file | head -n 2000 | bzip2 > $top_list

mkdir -p $output_2000_dir

python3 split_by_players.py $top_list $lichesss_raw_dir/*-{01..11}.pgn.bz2 $lichesss_raw_dir/*{3..8}-12.pgn.bz2 $output_2000_dir

rm -v $top_list

mkdir -p $output_2000_metadata_dir

python3 player_game_counts.py $output_2000_dir $output_2000_metadata_dir

python3 select_top_players.py $output_2000_metadata_dir \
        ${players_list}_train.csv $num_train \
        ${players_list}_validate.csv $num_val \
        ${players_list}_test.csv $num_test \

mkdir -p $final_data_dir
mkdir -p $final_data_dir/metadata
cp -v ${players_list}*.csv $final_data_dir/metadata

for c in "train" "validate" "test"; do
    mkdir $final_data_dir/${c}
    mkdir $final_data_dir/${c}_metadata
    for t in `tail -n +2 ${players_list}_${c}.csv|awk -F ',' '{print $1}'`; do
        cp -v ${output_2000_dir}/${t}.pgn.bz2 $final_data_dir/${c}
        cp ${output_2000_metadata_dir}/${t}.csv.bz2 $final_data_dir/${c}_metadata
    done
done
