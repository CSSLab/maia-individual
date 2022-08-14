#!/usr/bin/env python3
#
#    This file is part of Leela Zero.
#    Copyright (C) 2017-2018 Gian-Carlo Pascutto
#
#    Leela Zero is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.
#
#    Leela Zero is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with Leela Zero.  If not, see <http://www.gnu.org/licenses/>.

import numpy as np
import os
import os.path
import random
import tensorflow as tf
import time
import bisect
from .lc0_az_policy_map import make_map
import maia.proto.net_pb2 as pb

from .net import Net

from ..utils import printWithDate

import natsort


def model_path_gen(short_path):
    models_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../models'))
    return os.path.join(models_path, short_path, 'ckpt/ckpt-40')

class ApplySqueezeExcitation(tf.keras.layers.Layer):
    def __init__(self, **kwargs):
        super(ApplySqueezeExcitation, self).__init__(**kwargs)

    def build(self, input_dimens):
        self.reshape_size = input_dimens[1][1]

    def call(self, inputs):
        x = inputs[0]
        excited = inputs[1]
        gammas, betas = tf.split(tf.reshape(excited, [-1, self.reshape_size, 1, 1]), 2, axis=1)
        return tf.nn.sigmoid(gammas) * x + betas


class ApplyPolicyMap(tf.keras.layers.Layer):
    def __init__(self, **kwargs):
        super(ApplyPolicyMap, self).__init__(**kwargs)
        self.fc1 = tf.constant(make_map())

    def call(self, inputs):
        h_conv_pol_flat = tf.reshape(inputs, [-1, 80*8*8])
        return tf.matmul(h_conv_pol_flat, tf.cast(self.fc1, h_conv_pol_flat.dtype))

class TFProcess:
    def __init__(self, cfg, name, collection_name):
        tf.compat.v1.logging.set_verbosity(tf.compat.v1.logging.ERROR)

        self.cfg = cfg
        self.name = name
        self.collection_name = collection_name
        self.net = Net()
        self.root_dir = os.path.join('models', self.collection_name, self.name)

        # Network structure
        self.RESIDUAL_FILTERS = self.cfg['model']['filters']
        self.RESIDUAL_BLOCKS = self.cfg['model']['residual_blocks']
        self.SE_ratio = self.cfg['model']['se_ratio']
        self.policy_channels = self.cfg['model'].get('policy_channels', 32)
        precision = self.cfg['training'].get('precision', 'single')
        loss_scale = self.cfg['training'].get('loss_scale', 128)

        if precision == 'single':
            self.model_dtype = tf.float32
        elif precision == 'half':
            self.model_dtype = tf.float16
        else:
            raise ValueError("Unknown precision: {}".format(precision))

        # Scale the loss to prevent gradient underflow
        self.loss_scale = 1 if self.model_dtype == tf.float32 else loss_scale

        self.VALUE_HEAD = None

        self.POLICY_HEAD = pb.NetworkFormat.POLICY_CONVOLUTION

        self.net.set_policyformat(self.POLICY_HEAD)

        self.VALUE_HEAD = pb.NetworkFormat.VALUE_WDL
        self.wdl = True


        self.net.set_valueformat(self.VALUE_HEAD)

        self.swa_enabled = self.cfg['training'].get('swa', False)

        # Limit momentum of SWA exponential average to 1 - 1/(swa_max_n + 1)
        self.swa_max_n = self.cfg['training'].get('swa_max_n', 0)

        self.renorm_enabled = self.cfg['training'].get('renorm', False)
        self.renorm_max_r = self.cfg['training'].get('renorm_max_r', 1)
        self.renorm_max_d = self.cfg['training'].get('renorm_max_d', 0)
        self.renorm_momentum = self.cfg['training'].get('renorm_momentum', 0.99)

        gpus = tf.config.experimental.list_physical_devices('GPU')
        tf.config.experimental.set_visible_devices(gpus[self.cfg['gpu']], 'GPU')
        tf.config.experimental.set_memory_growth(gpus[self.cfg['gpu']], True)
        if self.model_dtype == tf.float16:
            tf.keras.mixed_precision.experimental.set_policy('mixed_float16')

        self.global_step = tf.Variable(0, name='global_step', trainable=False, dtype=tf.int64)

    def init_v2(self, train_dataset, test_dataset):
        self.train_dataset = train_dataset
        self.train_iter = iter(train_dataset)
        self.test_dataset = test_dataset
        self.test_iter = iter(test_dataset)
        self.init_net_v2()

    def init_net_v2(self):
        self.l2reg = tf.keras.regularizers.l2(l=0.5 * (0.0001))
        input_var = tf.keras.Input(shape=(112, 8*8))
        x_planes = tf.keras.layers.Reshape([112, 8, 8])(input_var)

        base_ckpt_path = model_path_gen(self.cfg['model']['path'])

        self.model_maia = tf.keras.Model(inputs=input_var, outputs=self.construct_net_complete(x_planes))
        self.checkpoint_restore = tf.train.Checkpoint(model=self.model_maia)
        self.restore_ckpt(base_ckpt_path)

        # The tf names use natural numbers with no prefixes
        # so to index layers correctly we neec to sort them naturally

        natsort_key = natsort.natsort_keygen()

        self.model = tf.keras.Model(
                inputs=input_var,
                outputs=self.construct_with_stops(
                    x_planes,
                    self.cfg['model'].get('back_prop_blocks', 3),
                    ))
        maia_layers = sorted(
            self.model_maia.layers,
            key = lambda x : natsort_key(x.name),
            )
        model_layers = sorted(
            [l for l in self.model.layers if 'lambda' not in l.name],
             key = lambda x : natsort_key(x.name),
             )

        layer_map = {model_layer.name : maia_layer for model_layer, maia_layer in zip(model_layers, maia_layers)}

        for i, model_layer in enumerate(self.model.layers):
            if not self.cfg['model'].get('keep_weights', False) and self.cfg['model'].get('back_prop_blocks', 3) > self.RESIDUAL_BLOCKS + 4:
                printWithDate(f"ending at depth {i}: {model_layer.name}")
                break
            # modify pretrained weights with gaussian noise
            if 'lambda' not in model_layer.name:
                # l_maia = layer_map[model_layer.name]
                # model_layer.set_weights([w.numpy() for w in l_maia.weights])

                multiplier = 0.01
                l_maia = layer_map[model_layer.name]
                new_weights = []
                for w in l_maia.weights:
                    layer_weight = w.numpy()
                    noise = np.random.normal(loc=0, scale=multiplier * np.std(layer_weight), size=layer_weight.shape)
                    layer_weight = layer_weight + noise
                    new_weights.append(layer_weight)

                model_layer.set_weights(new_weights)

            elif not self.cfg['model'].get('keep_weights', False):
                printWithDate(f"ending at depth {i}: {model_layer.name}")
                break

        printWithDate("Setting up lc0 stuff")
        # swa_count initialized reguardless to make checkpoint code simpler.
        self.swa_count = tf.Variable(0., name='swa_count', trainable=False)
        self.swa_weights = None
        if self.swa_enabled:
            # Count of networks accumulated into SWA
            self.swa_weights = [tf.Variable(w, trainable=False) for w in self.model.weights]

        self.active_lr = 0.01
        self.optimizer = tf.keras.optimizers.SGD(learning_rate=lambda: self.active_lr, momentum=0.9, nesterov=True)
        self.orig_optimizer = self.optimizer
        if self.loss_scale != 1:
            self.optimizer = tf.keras.mixed_precision.experimental.LossScaleOptimizer(self.optimizer, self.loss_scale)
        def correct_policy(target, output):
            output = tf.cast(output, tf.float32)
            # Calculate loss on policy head
            if self.cfg['training'].get('mask_legal_moves'):
                # extract mask for legal moves from target policy
                move_is_legal = tf.greater_equal(target, 0)
                # replace logits of illegal moves with large negative value (so that it doesn't affect policy of legal moves) without gradient
                illegal_filler = tf.zeros_like(output) - 1.0e10
                output = tf.where(move_is_legal, output, illegal_filler)
            # y_ still has -1 on illegal moves, flush them to 0
            target = tf.nn.relu(target)
            return target, output
        def policy_loss(target, output):
            target, output = correct_policy(target, output)
            policy_cross_entropy = \
                tf.nn.softmax_cross_entropy_with_logits(labels=tf.stop_gradient(target),
                                                        logits=output)
            return tf.reduce_mean(input_tensor=policy_cross_entropy)
        self.policy_loss_fn = policy_loss
        def policy_accuracy(target, output):
            target, output = correct_policy(target, output)
            return tf.reduce_mean(tf.cast(tf.equal(tf.argmax(input=target, axis=1), tf.argmax(input=output, axis=1)), tf.float32))
        self.policy_accuracy_fn = policy_accuracy


        q_ratio = self.cfg['training'].get('q_ratio', 0)
        assert 0 <= q_ratio <= 1

        # Linear conversion to scalar to compute MSE with, for comparison to old values
        wdl = tf.expand_dims(tf.constant([1.0, 0.0, -1.0]), 1)

        self.qMix = lambda z, q: q * q_ratio + z *(1 - q_ratio)
        # Loss on value head
        if self.wdl:
            def value_loss(target, output):
                output = tf.cast(output, tf.float32)
                value_cross_entropy = \
                    tf.nn.softmax_cross_entropy_with_logits(labels=tf.stop_gradient(target),
                                                    logits=output)
                return tf.reduce_mean(input_tensor=value_cross_entropy)
            self.value_loss_fn = value_loss
            def mse_loss(target, output):
                output = tf.cast(output, tf.float32)
                scalar_z_conv = tf.matmul(tf.nn.softmax(output), wdl)
                scalar_target = tf.matmul(target, wdl)
                return tf.reduce_mean(input_tensor=tf.math.squared_difference(scalar_target, scalar_z_conv))
            self.mse_loss_fn = mse_loss
        else:
            def value_loss(target, output):
                return tf.constant(0)
            self.value_loss_fn = value_loss
            def mse_loss(target, output):
                output = tf.cast(output, tf.float32)
                scalar_target = tf.matmul(target, wdl)
                return tf.reduce_mean(input_tensor=tf.math.squared_difference(scalar_target, output))
            self.mse_loss_fn = mse_loss

        pol_loss_w = self.cfg['training']['policy_loss_weight']
        val_loss_w = self.cfg['training']['value_loss_weight']
        self.lossMix = lambda policy, value: pol_loss_w * policy + val_loss_w * value

        def accuracy(target, output):
            output = tf.cast(output, tf.float32)
            return tf.reduce_mean(tf.cast(tf.equal(tf.argmax(input=target, axis=1), tf.argmax(input=output, axis=1)), tf.float32))
        self.accuracy_fn = accuracy

        self.avg_policy_loss = []
        self.avg_value_loss = []
        self.avg_mse_loss = []
        self.avg_reg_term = []
        self.time_start = None
        self.last_steps = None
        # Set adaptive learning rate during training
        self.cfg['training']['lr_boundaries'].sort()
        self.warmup_steps = self.cfg['training'].get('warmup_steps', 0)
        self.lr = self.cfg['training']['lr_values'][0]
        self.test_writer = tf.summary.create_file_writer(os.path.join(
                'runs',
                self.collection_name,
                self.name + '-test',
        ))
        self.train_writer = tf.summary.create_file_writer(os.path.join(
                'runs',
                self.collection_name,
                self.name + '-train',
        ))
        if self.swa_enabled:
            self.swa_writer = tf.summary.create_file_writer(os.path.join(
                    'runs',
                    self.collection_name,
                    self.name + '-swa-test',
            ))
        self.checkpoint = tf.train.Checkpoint(optimizer=self.orig_optimizer, model=self.model, global_step=self.global_step, swa_count=self.swa_count)
        self.checkpoint.listed = self.swa_weights
        self.manager = tf.train.CheckpointManager(
            self.checkpoint, directory=self.root_dir, max_to_keep=50, keep_checkpoint_every_n_hours=24)

    def replace_weights_v2(self, new_weights_orig):
        new_weights = [w for w in new_weights_orig]
        # self.model.weights ordering doesn't match up nicely, so first shuffle the new weights to match up.
        # input order is (for convolutional policy):
        # policy conv
        # policy bn * 4
        # policy raw conv and bias
        # value conv
        # value bn * 4
        # value dense with bias
        # value dense with bias
        #
        # output order is (for convolutional policy):
        # value conv
        # policy conv
        # value bn * 4
        # policy bn * 4
        # policy raw conv and bias
        # value dense with bias
        # value dense with bias
        new_weights[-5] = new_weights_orig[-10]
        new_weights[-6] = new_weights_orig[-11]
        new_weights[-7] = new_weights_orig[-12]
        new_weights[-8] = new_weights_orig[-13]
        new_weights[-9] = new_weights_orig[-14]
        new_weights[-10] = new_weights_orig[-15]
        new_weights[-11] = new_weights_orig[-5]
        new_weights[-12] = new_weights_orig[-6]
        new_weights[-13] = new_weights_orig[-7]
        new_weights[-14] = new_weights_orig[-8]
        new_weights[-15] = new_weights_orig[-16]
        new_weights[-16] = new_weights_orig[-9]

        all_evals = []
        offset = 0
        last_was_gamma = False
        for e, weights in enumerate(self.model.weights):
            source_idx = e+offset
            if weights.shape.ndims == 4:
                # Rescale rule50 related weights as clients do not normalize the input.
                if e == 0:
                    num_inputs = 112
                    # 50 move rule is the 110th input, or 109 starting from 0.
                    rule50_input = 109
                    for i in range(len(new_weights[source_idx])):
                        if (i % (num_inputs*9))//9 == rule50_input:
                            new_weights[source_idx][i] = new_weights[source_idx][i]*99

                # Convolution weights need a transpose
                #
                # TF (kYXInputOutput)
                # [filter_height, filter_width, in_channels, out_channels]
                #
                # Leela/cuDNN/Caffe (kOutputInputYX)
                # [output, input, filter_size, filter_size]
                s = weights.shape.as_list()
                shape = [s[i] for i in [3, 2, 0, 1]]
                new_weight = tf.constant(new_weights[source_idx], shape=shape)
                weights.assign(
                    tf.transpose(a=new_weight, perm=[2, 3, 1, 0]))
            elif weights.shape.ndims == 2:
                # Fully connected layers are [in, out] in TF
                #
                # [out, in] in Leela
                #
                s = weights.shape.as_list()
                shape = [s[i] for i in [1, 0]]
                new_weight = tf.constant(new_weights[source_idx], shape=shape)
                weights.assign(
                    tf.transpose(a=new_weight, perm=[1, 0]))
            else:
                # Can't populate renorm weights, but the current new_weight will need using elsewhere.
                if 'renorm' in weights.name:
                    offset-=1
                    continue
                # betas without gamms need to skip the gamma in the input.
                if 'beta:' in weights.name and not last_was_gamma:
                    source_idx+=1
                    offset+=1
                # Biases, batchnorm etc
                new_weight = tf.constant(new_weights[source_idx], shape=weights.shape)
                if 'stddev:' in weights.name:
                    weights.assign(tf.math.sqrt(new_weight + 1e-5))
                else:
                    weights.assign(new_weight)
                # need to use the variance to also populate the stddev for renorm, so adjust offset.
                if 'variance:' in weights.name and self.renorm_enabled:
                    offset-=1
            last_was_gamma = 'gamma:' in weights.name
        # Replace the SWA weights as well, ensuring swa accumulation is reset.
        if self.swa_enabled:
            self.swa_count.assign(tf.constant(0.))
            self.update_swa_v2()
        # This should result in identical file to the starting one
        # self.save_leelaz_weights_v2('restored.pb.gz')

    def restore_v2(self):
        if self.manager.latest_checkpoint is not None:
            print("Restoring from {0}".format(self.manager.latest_checkpoint))
            self.checkpoint.restore(self.manager.latest_checkpoint)

    def restore_ckpt(self, ckpt_path):
        print("loading lower weights from {}".format(ckpt_path))
        self.checkpoint_restore.restore(ckpt_path)

    def process_loop_v2(self, batch_size, test_batches, batch_splits=1):
        # Get the initial steps value in case this is a resume from a step count
        # which is not a multiple of total_steps.
        steps = self.global_step.read_value()
        total_steps = self.cfg['training']['total_steps']
        for _ in range(steps % total_steps, total_steps):
            self.process_v2(batch_size, test_batches, batch_splits=batch_splits)

    @tf.function()
    def read_weights(self):
        return [w.read_value() for w in self.model.weights]

    def get_reg_loss(self):
        '''
        Collect regularization losses based on where to freeze our model.
        Each entry in reg_loss_dict represents unique layers' regularization loss.
        Based on where to freeze, will add up reg loss correspondingly
        '''
        # from 0 to 10, 0 is after apply policy map, 10 is no freezing at all
        stop_point = self.cfg['model'].get('back_prop_blocks', 3)
        # empty for freezing at layer 0 and 1
        if stop_point == 0 or stop_point == 1:
            print("stopping at 0 or 1, no reg term applied")
            return []

        total_sections = self.RESIDUAL_BLOCKS + 4
        # stop_point will be <= 10
        if stop_point > total_sections:
            stop_point = total_sections

        stops = [i for i in range(0, total_sections + 1)]

        # make regularization loss dict
        reg_loss_dict = dict.fromkeys(stops, [])
        # define number of layers before residual tower to determine where each res block is in dict
        num_layers_before_res = 1

        for model_layer in self.model.layers:
            if 'conv_block1' in model_layer.name:
                reg_loss_dict[10] = reg_loss_dict[10] + model_layer.losses

            elif 'policy_head/conv_pol2' in model_layer.name:
                reg_loss_dict[2] = reg_loss_dict[2] + model_layer.losses

            elif 'policy_head/conv_pol1' in model_layer.name:
                reg_loss_dict[3] = reg_loss_dict[3] + model_layer.losses
            else:
                for i in range(0, self.RESIDUAL_BLOCKS):
                    res_block_name = 'res_{}'.format(i)
                    if res_block_name in model_layer.name:
                        res_index_in_section = total_sections - i - num_layers_before_res
                        reg_loss_dict[res_index_in_section] = reg_loss_dict[res_index_in_section] + model_layer.losses

        # for key, value in reg_loss_dict.items():
        #     print(key, len(value))

        reg_loss = []
        for i in range(2, stop_point + 1):
            reg_loss += reg_loss_dict[i]
        # print(reg_loss)
        print("stopping at {}".format(stop_point))
        print("collected {} regularization loss".format(len(reg_loss)))
        return reg_loss

    @tf.function()
    def process_inner_loop(self, x, y, z, q):
        with tf.GradientTape() as tape:
            policy, value = self.model(x, training=True)
            policy_loss = self.policy_loss_fn(y, policy)
            # reg_term = sum(self.model.losses)
            reg_term = sum(self.get_reg_loss())

            if self.wdl:
                value_loss = self.value_loss_fn(self.qMix(z, q), value)
                total_loss = self.lossMix(policy_loss, value_loss) + reg_term
            else:
                mse_loss = self.mse_loss_fn(self.qMix(z, q), value)
                total_loss = self.lossMix(policy_loss, mse_loss) + reg_term
            if self.loss_scale != 1:
                total_loss = self.optimizer.get_scaled_loss(total_loss)
        if self.wdl:
            mse_loss = self.mse_loss_fn(self.qMix(z, q), value)
        else:
            value_loss = self.value_loss_fn(self.qMix(z, q), value)
        return policy_loss, value_loss, mse_loss, reg_term, tape.gradient(total_loss, self.model.trainable_weights)

    def process_v2(self, batch_size, test_batches, batch_splits=1):
        if not self.time_start:
            self.time_start = time.time()

        # Get the initial steps value before we do a training step.
        steps = self.global_step.read_value()
        if not self.last_steps:
            self.last_steps = steps

        if self.swa_enabled:
            # split half of test_batches between testing regular weights and SWA weights
            test_batches //= 2
        # Run test before first step to see delta since end of last run.
        if steps % self.cfg['training']['total_steps'] == 0:
            # Steps is given as one higher than current in order to avoid it
            # being equal to the value the end of a run is stored against.
            self.calculate_test_summaries_v2(test_batches, steps + 1)
            if self.swa_enabled:
                self.calculate_swa_summaries_v2(test_batches, steps + 1)

        # Make sure that ghost batch norm can be applied
        if batch_size % 64 != 0:
            # Adjust required batch size for batch splitting.
            required_factor = 64 * \
                self.cfg['training'].get('num_batch_splits', 1)
            raise ValueError(
                'batch_size must be a multiple of {}'.format(required_factor))

        # Determine learning rate
        lr_values = self.cfg['training']['lr_values']
        lr_boundaries = self.cfg['training']['lr_boundaries']
        steps_total = steps % self.cfg['training']['total_steps']
        self.lr = lr_values[bisect.bisect_right(lr_boundaries, steps_total)]
        if self.warmup_steps > 0 and steps < self.warmup_steps:
            self.lr = self.lr * tf.cast(steps + 1, tf.float32) / self.warmup_steps

        # need to add 1 to steps because steps will be incremented after gradient update
        if (steps + 1) % self.cfg['training']['train_avg_report_steps'] == 0 or (steps + 1) % self.cfg['training']['total_steps'] == 0:
            before_weights = self.read_weights()

        x, y, z, q = next(self.train_iter)
        policy_loss, value_loss, mse_loss, reg_term, grads = self.process_inner_loop(x, y, z, q)

        # apply different learning rates to different layers
        new_grads_zip = zip(grads, self.model.trainable_variables)
        new_grads = []
        for (grad, var) in new_grads_zip:
            if 'conv_block1' in var.name:
                new_grads.append(grad * 0.05)
            elif 'res_0' in var.name:
                new_grads.append(grad * 0.1)
            elif 'res_1' in var.name:
                new_grads.append(grad * 0.25)
            elif 'res_2' in var.name:
                new_grads.append(grad * 0.4)
            elif 'res_3' in var.name:
                new_grads.append(grad * 0.55)
            elif 'res_4' in var.name:
                new_grads.append(grad * 0.7)
            elif 'res_5' in var.name:
                new_grads.append(grad * 0.85)
            else:
                new_grads.append(grad)

        grads = new_grads

        # Keep running averages
        # Google's paper scales MSE by 1/4 to a [0, 1] range, so do the same to
        # get comparable values.
        mse_loss /= 4.0
        self.avg_policy_loss.append(policy_loss)
        if self.wdl:
            self.avg_value_loss.append(value_loss)
        self.avg_mse_loss.append(mse_loss)
        self.avg_reg_term.append(reg_term)

        # Gradients of batch splits are summed, not averaged like usual, so need to scale lr accordingly to correct for this.
        self.active_lr = self.lr / batch_splits
        if self.loss_scale != 1:
            grads = self.optimizer.get_unscaled_gradients(grads)
        max_grad_norm = self.cfg['training'].get('max_grad_norm', 10000.0) * batch_splits
        grads, grad_norm = tf.clip_by_global_norm(grads, max_grad_norm)
        self.optimizer.apply_gradients([
            (grad, var)
            for (grad, var) in zip(grads, self.model.trainable_variables)
            if grad is not None
        ])

        # Update steps.
        self.global_step.assign_add(1)
        steps = self.global_step.read_value()

        if steps % self.cfg['training']['train_avg_report_steps'] == 0 or steps % self.cfg['training']['total_steps'] == 0:
            pol_loss_w = self.cfg['training']['policy_loss_weight']
            val_loss_w = self.cfg['training']['value_loss_weight']
            time_end = time.time()
            speed = 0
            if self.time_start:
                elapsed = time_end - self.time_start
                steps_elapsed = steps - self.last_steps
                speed = batch_size * (tf.cast(steps_elapsed, tf.float32) / elapsed)
            avg_policy_loss = np.mean(self.avg_policy_loss or [0])
            avg_value_loss = np.mean(self.avg_value_loss or [0])
            avg_mse_loss = np.mean(self.avg_mse_loss or [0])
            avg_reg_term = np.mean(self.avg_reg_term or [0])
            printWithDate("step {}, lr={:g} policy={:g} value={:g} mse={:g} reg={:g} total={:g} ({:g} pos/s)".format(
                steps, self.lr, avg_policy_loss, avg_value_loss, avg_mse_loss, avg_reg_term,
                pol_loss_w * avg_policy_loss + val_loss_w * avg_value_loss + avg_reg_term,
                speed))

            after_weights = self.read_weights()
            with self.train_writer.as_default():
                tf.summary.scalar("Policy Loss", avg_policy_loss, step=steps)
                tf.summary.scalar("Value Loss", avg_value_loss, step=steps)
                tf.summary.scalar("Reg term", avg_reg_term, step=steps)
                tf.summary.scalar("LR", self.lr, step=steps)
                tf.summary.scalar("Gradient norm", grad_norm / batch_splits, step=steps)
                tf.summary.scalar("MSE Loss", avg_mse_loss, step=steps)
                self.compute_update_ratio_v2(
                    before_weights, after_weights, steps)
            self.train_writer.flush()
            self.time_start = time_end
            self.last_steps = steps
            self.avg_policy_loss, self.avg_value_loss, self.avg_mse_loss, self.avg_reg_term = [], [], [], []

        if self.swa_enabled and steps % self.cfg['training']['swa_steps'] == 0:
            self.update_swa_v2()

        # Calculate test values every 'test_steps', but also ensure there is
        # one at the final step so the delta to the first step can be calculted.
        if steps % self.cfg['training']['test_steps'] == 0 or steps % self.cfg['training']['total_steps'] == 0:
            self.calculate_test_summaries_v2(test_batches, steps)
            if self.swa_enabled:
                self.calculate_swa_summaries_v2(test_batches, steps)

        # Save session and weights at end, and also optionally every 'checkpoint_steps'.
        if steps % self.cfg['training']['total_steps'] == 0 or (
                'checkpoint_steps' in self.cfg['training'] and steps % self.cfg['training']['checkpoint_steps'] == 0):
            self.manager.save()
            print("Model saved in file: {}".format(self.manager.latest_checkpoint))
            evaled_steps = steps.numpy()
            leela_path = self.manager.latest_checkpoint + "-" + str(evaled_steps)
            swa_path = self.manager.latest_checkpoint + "-swa-" + str(evaled_steps)
            self.net.pb.training_params.training_steps = evaled_steps
            self.save_leelaz_weights_v2(leela_path)
            print("Weights saved in file: {}".format(leela_path))
            if self.swa_enabled:
                self.save_swa_weights_v2(swa_path)
                print("SWA Weights saved in file: {}".format(swa_path))

    def calculate_swa_summaries_v2(self, test_batches, steps):
        backup = self.read_weights()
        for (swa, w) in zip(self.swa_weights, self.model.weights):
            w.assign(swa.read_value())
        true_test_writer, self.test_writer = self.test_writer, self.swa_writer
        print('swa', end=' ')
        self.calculate_test_summaries_v2(test_batches, steps)
        self.test_writer = true_test_writer
        for (old, w) in zip(backup, self.model.weights):
            w.assign(old)

    @tf.function()
    def calculate_test_summaries_inner_loop(self, x, y, z, q):
        policy, value = self.model(x, training=False)
        policy_loss = self.policy_loss_fn(y, policy)
        policy_accuracy = self.policy_accuracy_fn(y, policy)
        if self.wdl:
            value_loss = self.value_loss_fn(self.qMix(z, q), value)
            mse_loss = self.mse_loss_fn(self.qMix(z, q), value)
            value_accuracy = self.accuracy_fn(self.qMix(z,q), value)
        else:
            value_loss = self.value_loss_fn(self.qMix(z, q), value)
            mse_loss = self.mse_loss_fn(self.qMix(z, q), value)
            value_accuracy = tf.constant(0.)
        return policy_loss, value_loss, mse_loss, policy_accuracy, value_accuracy

    def calculate_test_summaries_v2(self, test_batches, steps):
        sum_policy_accuracy = 0
        sum_value_accuracy = 0
        sum_mse = 0
        sum_policy = 0
        sum_value = 0
        for _ in range(0, test_batches):
            x, y, z, q = next(self.test_iter)
            policy_loss, value_loss, mse_loss, policy_accuracy, value_accuracy = self.calculate_test_summaries_inner_loop(x, y, z, q)
            sum_policy_accuracy += policy_accuracy
            sum_mse += mse_loss
            sum_policy += policy_loss
            if self.wdl:
                sum_value_accuracy += value_accuracy
                sum_value += value_loss
        sum_policy_accuracy /= test_batches
        sum_policy_accuracy *= 100
        sum_policy /= test_batches
        sum_value /= test_batches
        if self.wdl:
            sum_value_accuracy /= test_batches
            sum_value_accuracy *= 100
        # Additionally rescale to [0, 1] so divide by 4
        sum_mse /= (4.0 * test_batches)
        self.net.pb.training_params.learning_rate = self.lr
        self.net.pb.training_params.mse_loss = sum_mse
        self.net.pb.training_params.policy_loss = sum_policy
        # TODO store value and value accuracy in pb
        self.net.pb.training_params.accuracy = sum_policy_accuracy
        with self.test_writer.as_default():
            tf.summary.scalar("Policy Loss", sum_policy, step=steps)
            tf.summary.scalar("Value Loss", sum_value, step=steps)
            tf.summary.scalar("MSE Loss", sum_mse, step=steps)
            tf.summary.scalar("Policy Accuracy", sum_policy_accuracy, step=steps)
            if self.wdl:
                tf.summary.scalar("Value Accuracy", sum_value_accuracy, step=steps)
            for w in self.model.weights:
                tf.summary.histogram(w.name, w, buckets=1000, step=steps)
        self.test_writer.flush()

        printWithDate("step {}, policy={:g} value={:g} policy accuracy={:g}% value accuracy={:g}% mse={:g}".\
            format(steps, sum_policy, sum_value, sum_policy_accuracy, sum_value_accuracy, sum_mse))

    @tf.function()
    def compute_update_ratio_v2(self, before_weights, after_weights, steps):
        """Compute the ratio of gradient norm to weight norm.

        Adapted from https://github.com/tensorflow/minigo/blob/c923cd5b11f7d417c9541ad61414bf175a84dc31/dual_net.py#L567
        """
        deltas = [after - before for after,
                  before in zip(after_weights, before_weights)]
        delta_norms = [tf.math.reduce_euclidean_norm(d) for d in deltas]
        weight_norms = [tf.math.reduce_euclidean_norm(w) for w in before_weights]
        ratios = [(tensor.name, tf.cond(w != 0., lambda: d / w, lambda: -1.)) for d, w, tensor in zip(delta_norms, weight_norms, self.model.weights) if not 'moving' in tensor.name]
        for name, ratio in ratios:
            tf.summary.scalar('update_ratios/' + name, ratio, step=steps)
        # Filtering is hard, so just push infinities/NaNs to an unreasonably large value.
        ratios = [tf.cond(r > 0, lambda: tf.math.log(r) / 2.30258509299, lambda: 200.) for (_, r) in ratios]
        tf.summary.histogram('update_ratios_log10', tf.stack(ratios), buckets=1000, step=steps)

    def update_swa_v2(self):
        num = self.swa_count.read_value()
        for (w, swa) in zip(self.model.weights, self.swa_weights):
            swa.assign(swa.read_value() * (num / (num + 1.)) + w.read_value() * (1. / (num + 1.)))
        self.swa_count.assign(min(num + 1., self.swa_max_n))

    def save_swa_weights_v2(self, filename):
        backup = self.read_weights()
        for (swa, w) in zip(self.swa_weights, self.model.weights):
            w.assign(swa.read_value())
        self.save_leelaz_weights_v2(filename)
        for (old, w) in zip(backup, self.model.weights):
            w.assign(old)

    def save_leelaz_weights_v2(self, filename):
        all_tensors = []
        all_weights = []
        last_was_gamma = False
        for weights in self.model.weights:
            work_weights = None
            if weights.shape.ndims == 4:
                # Convolution weights need a transpose
                #
                # TF (kYXInputOutput)
                # [filter_height, filter_width, in_channels, out_channels]
                #
                # Leela/cuDNN/Caffe (kOutputInputYX)
                # [output, input, filter_size, filter_size]
                work_weights = tf.transpose(a=weights, perm=[3, 2, 0, 1])
            elif weights.shape.ndims == 2:
                # Fully connected layers are [in, out] in TF
                #
                # [out, in] in Leela
                #
                work_weights = tf.transpose(a=weights, perm=[1, 0])
            else:
                # batch renorm has extra weights, but we don't know what to do with them.
                if 'renorm' in weights.name:
                    continue
                # renorm has variance, but it is not the primary source of truth
                if 'variance:' in weights.name and self.renorm_enabled:
                    continue
                # Renorm has moving stddev not variance, undo the transform to make it compatible.
                if 'stddev:' in weights.name:
                    all_tensors.append(tf.math.square(weights) - 1e-5)
                    continue
                # Biases, batchnorm etc
                # pb expects every batch norm to have gammas, but not all of our
                # batch norms have gammas, so manually add pretend gammas.
                if 'beta:' in weights.name and not last_was_gamma:
                    all_tensors.append(tf.ones_like(weights))
                work_weights = weights.read_value()
            all_tensors.append(work_weights)
            last_was_gamma = 'gamma:' in weights.name

        # HACK: model weights ordering is some kind of breadth first traversal,
        # but pb expects a specific ordering which BFT is not a match for once
        # we get to the heads. Apply manual permutation.
        # This is fragile and at minimum should have some checks to ensure it isn't breaking things.
        #TODO: also support classic policy head as it has a different set of layers and hence changes the permutation.
        permuted_tensors = [w for w in all_tensors]
        permuted_tensors[-5] = all_tensors[-11]
        permuted_tensors[-6] = all_tensors[-12]
        permuted_tensors[-7] = all_tensors[-13]
        permuted_tensors[-8] = all_tensors[-14]
        permuted_tensors[-9] = all_tensors[-16]
        permuted_tensors[-10] = all_tensors[-5]
        permuted_tensors[-11] = all_tensors[-6]
        permuted_tensors[-12] = all_tensors[-7]
        permuted_tensors[-13] = all_tensors[-8]
        permuted_tensors[-14] = all_tensors[-9]
        permuted_tensors[-15] = all_tensors[-10]
        permuted_tensors[-16] = all_tensors[-15]
        all_tensors = permuted_tensors

        for e, nparray in enumerate(all_tensors):
            # Rescale rule50 related weights as clients do not normalize the input.
            if e == 0:
                num_inputs = 112
                # 50 move rule is the 110th input, or 109 starting from 0.
                rule50_input = 109
                wt_flt = []
                for i, weight in enumerate(np.ravel(nparray)):
                    if (i % (num_inputs*9))//9 == rule50_input:
                        wt_flt.append(weight/99)
                    else:
                        wt_flt.append(weight)
            else:
                wt_flt = [wt for wt in np.ravel(nparray)]
            all_weights.append(wt_flt)

        self.net.fill_net(all_weights)
        self.net.save_proto(filename)

    def set_name(self, name, suffix):
        return None if not name else "{}/{}".format(name, suffix)

    def batch_norm_v2(self, input, scale=False, name=None):
        if self.renorm_enabled:
            clipping = {
                "rmin": 1.0/self.renorm_max_r,
                "rmax": self.renorm_max_r,
                "dmax": self.renorm_max_d
                }
            return tf.keras.layers.BatchNormalization(
                epsilon=1e-5, axis=1, fused=False, center=True,
                scale=scale, renorm=True, renorm_clipping=clipping,
                renorm_momentum=self.renorm_momentum, name=self.set_name(name,'batchnorm'))(input)
        else:
            return tf.keras.layers.BatchNormalization(
                epsilon=1e-5, axis=1, fused=False, center=True,
                scale=scale, virtual_batch_size=64, name=self.set_name(name,'batchnorm'))(input)

    def squeeze_excitation_v2(self, inputs, channels, name):
        assert channels % self.SE_ratio == 0

        pooled = tf.keras.layers.GlobalAveragePooling2D(data_format='channels_first', name=self.set_name(name,'global_avgpool'))(inputs)
        squeezed = tf.keras.layers.Activation('relu', name=self.set_name(name,'activation'))(tf.keras.layers.Dense(channels // self.SE_ratio, kernel_initializer='glorot_normal', kernel_regularizer=self.l2reg, name=self.set_name(name,'dense_1'))(pooled))
        excited = tf.keras.layers.Dense(2 * channels, kernel_initializer='glorot_normal', kernel_regularizer=self.l2reg, name=self.set_name(name,'dense_2'))(squeezed)
        return ApplySqueezeExcitation(name=self.set_name(name,'squeeze_excitation'))([inputs, excited])

    def conv_block_v2(self, inputs, filter_size, output_channels, bn_scale=False, name=None):
        conv = tf.keras.layers.Conv2D(output_channels, filter_size, use_bias=False, padding='same', kernel_initializer='glorot_normal', kernel_regularizer=self.l2reg, data_format='channels_first', name=self.set_name(name,'conv2d'))(inputs)
        return tf.keras.layers.Activation('relu', name=self.set_name(name,'activation'))(self.batch_norm_v2(conv, scale=bn_scale, name=None if not name else name))

    def residual_block_v2(self, inputs, channels, name=None):
        conv1 = tf.keras.layers.Conv2D(channels, 3, use_bias=False, padding='same', kernel_initializer='glorot_normal', kernel_regularizer=self.l2reg, data_format='channels_first', name=self.set_name(name,'conv2d_1'))(inputs)
        out1 = tf.keras.layers.Activation('relu', name=self.set_name(name,'activation_1'))(self.batch_norm_v2(conv1, scale=False, name = None if not name else (name + '/bn_1')))
        conv2 = tf.keras.layers.Conv2D(channels, 3, use_bias=False, padding='same', kernel_initializer='glorot_normal', kernel_regularizer=self.l2reg, data_format='channels_first', name=self.set_name(name,'conv2d_2'))(out1)
        out2 = self.squeeze_excitation_v2(self.batch_norm_v2(conv2, scale=True, name = None if not name else (name + '/bn_2')), channels, None if not name else (name + '/se_block'))
        return tf.keras.layers.Activation('relu', name=self.set_name(name,'activation_2'))(tf.keras.layers.add([inputs, out2], name=self.set_name(name,'add')))

    def construct_net_complete(self, inputs):
        flow = self.conv_block_v2(inputs, filter_size=3, output_channels=self.RESIDUAL_FILTERS, bn_scale=True, name='conv_block1')

        for _ in range(0, self.RESIDUAL_BLOCKS):
            flow = self.residual_block_v2(flow, self.RESIDUAL_FILTERS, name='res_tower/res_{}'.format(_))

        # Policy head
        conv_pol = self.conv_block_v2(flow, filter_size=3, output_channels=self.RESIDUAL_FILTERS, name='policy_head/conv_pol1')
        conv_pol2 = tf.keras.layers.Conv2D(80, 3, use_bias=True, padding='same', kernel_initializer='glorot_normal', kernel_regularizer=self.l2reg, bias_regularizer=self.l2reg, data_format='channels_first', name='policy_head/conv_pol2')(conv_pol)
        h_fc1 = ApplyPolicyMap(name='policy_head/h_fc1')(conv_pol2)

        # Value head
        conv_val = self.conv_block_v2(flow, filter_size=1, output_channels=32, name='value_head/conv_val')
        h_conv_val_flat = tf.keras.layers.Flatten(name='value_head/flatten')(conv_val)
        h_fc2 = tf.keras.layers.Dense(128, kernel_initializer='glorot_normal', kernel_regularizer=self.l2reg, activation='relu', name='value_head/dense_1')(h_conv_val_flat)
        h_fc3 = tf.keras.layers.Dense(3, kernel_initializer='glorot_normal', kernel_regularizer=self.l2reg, bias_regularizer=self.l2reg, name='value_head/dense_2')(h_fc2)
        return h_fc1, h_fc3

    def construct_with_stops(self, inputs, num_sections, from_top = True):

        tot_sections = self.RESIDUAL_BLOCKS + 4
        if from_top:
            num_sections = tot_sections - num_sections
        #section_count = 0 or less is no stops
        section_count = 1

        flow_p = self.conv_block_v2(inputs, filter_size=3, output_channels=self.RESIDUAL_FILTERS, bn_scale=True, name='conv_block1')
        if section_count == num_sections:
            flow_p = tf.keras.layers.Lambda(lambda x: tf.keras.backend.stop_gradient(x))(flow_p)
            printWithDate(f"Adding stop at depth: {section_count}")

        for _ in range(0, self.RESIDUAL_BLOCKS):

            section_count += 1
            flow_p = self.residual_block_v2(flow_p, self.RESIDUAL_FILTERS, name='res_towers/res_{}'.format(_))
            if section_count == num_sections:
                flow_p = tf.keras.layers.Lambda(lambda x: tf.keras.backend.stop_gradient(x))(flow_p)
                printWithDate(f"Adding stop at depth: {section_count}")

        section_count += 1
        conv_pol = self.conv_block_v2(flow_p, filter_size=3, output_channels=self.RESIDUAL_FILTERS, name='policy_head/conv_pol1')
        if section_count == num_sections:
            conv_pol = tf.keras.layers.Lambda(lambda x: tf.keras.backend.stop_gradient(x))(conv_pol)
            printWithDate(f"Adding stop at depth: {section_count}")

        section_count += 1
        conv_pol2 = tf.keras.layers.Conv2D(80, 3, use_bias=True, padding='same', kernel_initializer='glorot_normal', kernel_regularizer=self.l2reg, bias_regularizer=self.l2reg, data_format='channels_first', name='policy_head/conv_pol2')(conv_pol)
        if section_count == num_sections:
            conv_pol2 = tf.keras.layers.Lambda(lambda x: tf.keras.backend.stop_gradient(x))(conv_pol2)
            printWithDate(f"Adding stop at depth: {section_count}")

        section_count += 1
        h_fc1 = ApplyPolicyMap(name='policy_head/h_fc1')(conv_pol2)
        if section_count == num_sections:
            h_fc1 = tf.keras.layers.Lambda(lambda x: tf.keras.backend.stop_gradient(x))(h_fc1)
            printWithDate(f"Adding stop at depth: {section_count}")

        if section_count != tot_sections:
            raise RuntimeError(f"Number of sections was calculated to be {tot_sections}, but is actually {section_count}")

        # Value head
        flow_v = tf.keras.layers.Lambda(lambda x: tf.keras.backend.stop_gradient(x))(flow_p)
        conv_val = self.conv_block_v2(flow_v, filter_size=1, output_channels=32, name='value_head/conv_val')
        h_conv_val_flat = tf.keras.layers.Flatten(name='value_head/flatten')(conv_val)
        h_fc2 = tf.keras.layers.Dense(128, kernel_initializer='glorot_normal', kernel_regularizer=self.l2reg, activation='relu', name='value_head/dense_1')(h_conv_val_flat)
        h_fc3 = tf.keras.layers.Dense(3, kernel_initializer='glorot_normal', kernel_regularizer=self.l2reg, bias_regularizer=self.l2reg, name='value_head/dense_2')(h_fc2)


        return h_fc1, h_fc3

