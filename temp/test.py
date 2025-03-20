# from dotenv import load_dotenv
# load_dotenv()

import os
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3' 
# os.environ['CUDA_VISIBLE_DEVICES'] = '-1'

import tensorflow as tf
# tf.get_logger().setLevel('ERROR')

print(tf.config.list_physical_devices('GPU'))
