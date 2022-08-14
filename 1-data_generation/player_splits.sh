#!/bin/bash -e

input_files="../../data/top_player_games"
output_files="../../data/transfer_players_pgns_split"
mkdir -p $output_files

train_frac=80
val_frac=10
test_frac=10

for p in $input_files/*; do
    name=`basename $p`
    p_name=${name%.pgn.bz2}
    split_dir=$output_files/$name
    mkdir $split_dir

    screen -S "${p_name}" -dm bash -c "python3 pgn_fractional_split.py $p $split_dir/train.pgn.bz2 $split_dir/validate.pgn.bz2 $split_dir/test.pgn.bz2 --ratios $train_frac $val_frac $test_frac"
done
