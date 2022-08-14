import io
import tempfile

import tensorflow as tf

def show_model(model, filename = None, detailed = False, show_shapes = False):
    if filename is None:
        tempf = tempfile.NamedTemporaryFile(suffix='.png')
        filename = tempf.name
    return tf.keras.utils.plot_model(
                        model,
                        to_file=filename,
                        show_shapes=show_shapes,
                        show_layer_names=True,
                        rankdir='TB',
                        expand_nested=detailed,
                        dpi=96,
        )
