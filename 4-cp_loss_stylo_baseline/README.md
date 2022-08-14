`cp_loss_hist`: This is where i save all the train/validation/test data for adding up all games

`cp_loss_count_per_game`: This is where i save all the train/validation/test data per game. Note the counts haven't been normalized.

`cp_loss_hist_per_move`: This is where i save all the train/validation/test data per move adding up all games.

`cp_loss_hist_per_move_per_game`: This is where i save all the train/validation/test data per move per game.

`cp_loss_hist_per_move_per_game_count`: This is where i save all the train/validation/test data per move per game in counts so they can be added later.

`get_cp_loss.py`: Parsing code to get cp_loss and its histograms for both train and extended players, and save them in format of **.npy**

`get_cp_loss_per_game.py`: Parsing code to get cp_loss and its histograms (counts) for extended players for each game, and save them in format of **.npy**. Note I don't normalize when saving, so I can sweep across it to get parametrization of num_games.

`get_cp_loss_per_move.py`: Parsing code to get cp_loss and its histograms for both train and extended players for all games by moves, and save them in format of **.npy**. 

`get_cp_loss_per_move_per_game.py`: Parsing code to get cp_loss and its histograms for both train and extended players for each game by moves, and save them in format of **.npy**. 

`get_cp_loss_per_move_per_game_count`: Parsing code to get cp_loss and its histograms (counts) for both train and extended players for each game by moves, and save them in format of **.npy**. 

`test_all_games.py`: Baseline to test accuracy using all games instead of individual games, with Euclidean Distance or Naive Bayes. Data is from `cp_loss_hist`.

`sweep_num_games.py`: Baseline using Euclidean Distance or Naive Bayes. Training Data is from `cp_loss_hist` and Test Data is from `cp_loss_count_per_game`. Will sweep across [1, 2, 4, 8, 16] number of games.

`sweep_moves_per_game.py`: Naive Bayes on per move evaluation. This is done on average accuracy for each game. Training data is from `cp_loss_hist_per_move`, Test data is from `cp_loss_hist_per_move_per_game`.

`sweep_moves_all_games.py`: Naive Bayes on per move evaluation. This is done on average accuracy for each game. Data is from `cp_loss_hist_per_move`

`sweep_moves_num_games.py`: Naive Bayes on per move evaluation given number of games. Training data is from `cp_loss_hist_per_move`, Test data is from `cp_loss_hist_per_move_per_game_count`. Set it to 1 will be same as `sweep_moves_per_game.py`

`train_cploss_per_game.py`: Baseline using simple neural network with 2 fully-connected layer. Training on each game, and also evaluate per game accuracy. **This now gives nan value when training on 30 players.**
