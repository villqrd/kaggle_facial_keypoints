import multiprocessing
import tensorflow as tf
from tensorflow.contrib.layers import fully_connected

IMG_SIZE = 96
TRAIN, EVAL, PREDICT = 'TRAIN', 'EVAL', 'PREDICT'


def conv_relu(inputs, kernel_size, strides, depth):
    """
    Creates a convolutional layer, with relu activation function
    
    :param inputs: Input Tensor with shape [None, width, height, depth]
    :param kernel_size: Size of the kernel (assumed square)
    :param strides: strides length, only for
    :param depth: number of feature
    :return: the convolutional layer
    """
    w = tf.get_variable(
        'weights',
        shape=[kernel_size, kernel_size, inputs.shape[3], depth],
        initializer=tf.contrib.layers.xavier_initializer(),
    )
    b = tf.get_variable(
        'biases',
        shape=[depth],
        initializer=tf.constant_initializer(0.0),
    )
    conv = tf.nn.conv2d(inputs, filter=w, strides=[1, strides, strides, 1], padding='SAME') + b
    return tf.nn.relu(conv)


def full_pass(inputs, convs, p_keep):
    """
    Full pass through the CNN
    
    :param inputs: Tensor with shape [None, width, height, depth], input images to the model
    :param convs: (list) architecture of the CNN, e.g. [32, 64, 128]
    :param p_keep: probability to keep a unit when applying drop out
    :return: Tensor with shape [?, 30], outputs location of the areas of interest
    """
    ip = inputs
    for i, c in enumerate(convs):
        with tf.variable_scope('conv_{}'.format(i)):
            ip = conv_relu(ip, 3, 1, c)
            ip = tf.nn.max_pool(ip, [1, 2, 2, 1], [1, 2, 2, 1], padding='SAME')
            ip = tf.contrib.layers.dropout(ip, p_keep, is_training=is_training)
    shape = ip.get_shape().as_list()
    ip = tf.reshape(ip, [-1, shape[1] * shape[2] * shape[3]])
    with tf.variable_scope('fc_4'):
        ip = fully_connected(ip, 1000, activation_fn=tf.nn.relu)
        ip = tf.contrib.layers.dropout(ip, p_keep, is_training=is_training)
    with tf.variable_scope('out'):
        return fully_connected(ip, 30, activation_fn=None)


def model_fn(mode,
             inputs,
             labels,
             learning_rate=0.1,
             convs=None,
             p_keep=1.0):
    """
    Adds necessary nodes to graph and returns ops to be evaluated
    
    :param mode: TRAIN, EVAL, PREDICT depending on usage
    :param inputs: Tensor with shape [None, width, height, depth], input images to the model
    :param labels: Tensor with shape [None, n_labels] to be predicted, None if mode is Predict
    :param learning_rate: rate in SGD, None if mode is Predict
    :param convs: (list) architecture of the CNN, e.g. [32, 64, 128]
    :param p_keep: probability to keep a unit when applying drop out, None if mode is Predict
    :return: The ops to be evaluated
    """
    pred = full_pass(inputs, convs, p_keep, mode == TRAIN)
    if mode in (TRAIN, EVAL):
        global_step = tf.contrib.framework.get_or_create_global_step()
        loss = tf.reduce_mean(tf.square(pred - labels))
        tf.summary.scalar('loss', loss)

    if mode == PREDICT:
        return {
            'predictions': pred,
        }

    if mode == TRAIN:
        optimizer = tf.train.AdamOptimizer(learning_rate=learning_rate)
        train_op = optimizer.minimize(loss, global_step=global_step)
        return global_step, train_op

    if mode == EVAL:
        return {
            'loss': loss,
        }


def input_fn(filenames,
             batch_size,
             num_epochs=None,
             shuffle=False):
    """
    Creates data pipeline.
    
    :param filenames: (list) filenames of the inputs
    :param batch_size: size of the batches
    :param num_epochs: number of epochs
    :param shuffle: flag to indicate whether to shuffle (True) or not
    :return: a list of inputs ops
    """
    reader = tf.TFRecordReader()
    filename_queue = tf.train.string_input_producer(filenames, num_epochs=num_epochs)
    _, serialized_example = reader.read(filename_queue)
    features = tf.parse_single_example(
        serialized_example,
        features={
            'height': tf.FixedLenFeature([], tf.int64),
            'width': tf.FixedLenFeature([], tf.int64),
            'image_raw': tf.FixedLenFeature([], tf.string),
            'labels': tf.FixedLenFeature([30], tf.float32)
        }
    )

    label = tf.cast(features['labels'], tf.float32)
    image = tf.decode_raw(features['image_raw'], tf.uint8)
    image = tf.to_float(image) / 255.
    image = tf.reshape(image, [IMG_SIZE, IMG_SIZE, 1])
    if shuffle:
        images, labels = tf.train.batch([image, label],
                                        batch_size,
                                        allow_smaller_final_batch=True,
                                        num_threads=multiprocessing.cpu_count())
    else:
        images, labels = tf.train.shuffle_batch([image, label],
                                                batch_size,
                                                capacity=batch_size * 10,
                                                min_after_dequeue=batch_size * 2 + 1,
                                                allow_smaller_final_batch=True,
                                                num_threads=multiprocessing.cpu_count())
    return images, labels