#!/usr/bin/env python
#encoding=utf8
'''
  Author: zldeng
  create@2017-08-11 10:50:43
'''

import sys

reload(sys)
sys.path.append('../BaseUtil')

import tensorflow as tf
import numpy as np
import os,time,datetime
import pickle
from tensorflow.contrib import learn

from sklearn.model_selection import train_test_split
from sklearn.preprocessing import OneHotEncoder
from sklearn.preprocessing import LabelEncoder
from sklearn import preprocessing
from CNNModel import TextCNN
from DataUtil import loadLabeledData
from DataUtil import batch_iter


#configuration
tf.flags.DEFINE_float("learning_rate",0.01,"learning rate")

tf.flags.DEFINE_integer("num_epochs",60,"embedding size")
tf.flags.DEFINE_integer("batch_size", 64, "Batch size for training/evaluating.") 
tf.flags.DEFINE_integer("validate_every", 5, "Validate every validate_every epochs.") 

tf.flags.DEFINE_integer("decay_steps", 12000, "how many steps before decay learning rate.")
tf.flags.DEFINE_float("decay_rate", 0.9, "Rate of decay for learning rate.") #0.5一次衰减多少

tf.flags.DEFINE_string("ckpt_dir","text_cnn_checkpoint/","checkpoint location for the model")
tf.flags.DEFINE_integer('num_checkpoints',10,'save checkpoints count')

tf.flags.DEFINE_integer("embed_size",128,"embedding size")
tf.flags.DEFINE_string("filter_sizes", "3,4,5", "Comma-separated filter sizes (default: '3,4,5')")
tf.flags.DEFINE_integer("num_filters", 128, "Number of filters per filter size (default: 128)")

tf.flags.DEFINE_boolean("is_training",True,"is traning.true:tranining,false:testing/inference")

tf.flags.DEFINE_float('validation_percentage',0.1,'validat data percentage in train data')
tf.flags.DEFINE_integer('max_sentence_length',30,'max words count in a sentence')
tf.flags.DEFINE_float("dropout_keep_prob", 0.5, "Dropout keep probability (default: 0.5)")

tf.flags.DEFINE_float("l2_reg_lambda", 0.0001, "L2 regularization lambda (default: 0.0)")

tf.flags.DEFINE_boolean("allow_soft_placement", True, "Allow device soft device placement")
tf.flags.DEFINE_boolean("log_device_placement", False, "Log placement of ops on devices")


tf.flags.DEFINE_string("train_data","/home/dengzhilong/code_from_my_git/data/parser_engine/parser.model.train.tag2",
	"path of traning data.")

tf.flags.DEFINE_string("label_encoder",'label_encoder','label encoder name')
FLAGS=tf.flags.FLAGS
FLAGS._parse_flags()

timestamp = str(int(time.time()))
out_dir = os.path.abspath(os.path.join(os.path.curdir, "runs_hn_cnn", timestamp))

if not os.path.exists(out_dir):
	os.makedirs(out_dir)

for attr,value in sorted(FLAGS.__flags.items()):
	sys.stderr.write("{}={}".format(attr,value) + '\n')

sys.stderr.write('begin train....\n')
sys.stderr.write('begin load train data and create vocabulary...\n')

labeled_data_id,labeled_data_X,labeled_data_y = loadLabeledData(FLAGS.train_data) 

#encode label to int
label_encoder = preprocessing.LabelEncoder()
labeled_data_y = label_encoder.fit_transform(labeled_data_y)

label_encoder_name = os.path.join(out_dir,FLAGS.label_encoder)
#save label_encoder to file
pickle.dump(label_encoder,file(label_encoder_name,'wb'),True)

#convet label to int array
label_cnt = len(label_encoder.classes_)
sample_cnt = len(labeled_data_X)
labeled_y = np.zeros([sample_cnt,label_cnt])
for sample_idx,label_idx in enumerate(labeled_data_y):
	labeled_y[sample_idx][label_idx] = 1

max_sentence_len = min(FLAGS.max_sentence_length,max([len(s.split(' ')) for s in labeled_data_X]))
vocab_processor = learn.preprocessing.VocabularyProcessor(max_sentence_len)

labeled_data_X = np.array(list(vocab_processor.fit_transform(labeled_data_X)))

x_train,x_dev,y_train,y_dev = train_test_split(labeled_data_X,labeled_y,test_size = FLAGS.validation_percentage)

x_train = np.array(x_train)
y_train = np.array(y_train)

x_dev = np.array(x_dev)
y_dev = np.array(y_dev)

with tf.Graph().as_default():
	sess_conf = tf.ConfigProto(
		allow_soft_placement=FLAGS.allow_soft_placement,
		log_device_placement=FLAGS.log_device_placement)

	sess = tf.Session(config = sess_conf)

	with sess.as_default():
		checkpoint_dir = os.path.abspath(os.path.join(out_dir,FLAGS.ckpt_dir))
		if not os.path.exists(checkpoint_dir):
			os.makedirs(checkpoint_dir)
		
		checkpoints_prefix = os.path.join(checkpoint_dir,'model')

		vocab_processor.save(os.path.join(out_dir,'vocab'))
		
		filter_sizes_list = [int(val) for val in FLAGS.filter_sizes.split(',')]		
		rnn = TextCNN(sequence_length = x_train.shape[1],
			num_classes = y_train.shape[1],
			vocab_size = len(vocab_processor.vocabulary_),
			embeding_size = FLAGS.embed_size,
			filter_sizes = filter_sizes_list,
			num_filters = FLAGS.num_filters,
			l2_reg_lambda = FLAGS.l2_reg_lambda,
			learning_rate = FLAGS.learning_rate,
			decay_steps = FLAGS.decay_steps,
			decay_rate = FLAGS.decay_rate)


		saver = tf.train.Saver(tf.global_variables(),max_to_keep = FLAGS.num_checkpoints)
		
		sess.run(tf.global_variables_initializer())


		def train_step(x_batch,y_batch):
			feed_dict = {
				rnn.input_x : x_batch,
				rnn.input_y : y_batch,
				rnn.dropout_keep_prob:FLAGS.dropout_keep_prob
				}

			tmp,step,loss,accuracy = sess.run([rnn.train_op,rnn.global_step,rnn.loss_val,rnn.accuracy],feed_dict)

			time_str = datetime.datetime.now().isoformat()
			print "{}:step {}, loss {:g}, acc {:g}".format(time_str,step,loss,accuracy)
			

		def dev_step(x_batch,y_batch):
			feed_dict = {
				rnn.input_x : x_batch,
				rnn.input_y : y_batch,
				rnn.dropout_keep_prob:1.0
				}
			

			step,loss,accuracy = sess.run([rnn.global_step,rnn.loss_val,rnn.accuracy],feed_dict)
			
			time_str = datetime.datetime.now().isoformat()
			print "dev_result: {}:step {}, loss {:g}, acc {:g}".format(time_str,step,loss,accuracy)

		
		for epoch_idx in range(FLAGS.num_epochs):
			batches = batch_iter(list(zip(x_train,y_train)),FLAGS.batch_size) 
				
			for batch in batches:
				x_batch,y_batch = zip(*batch)
				
				train_step(x_batch,y_batch)

				if epoch_idx % FLAGS.validate_every == 0:
					print '\n'
					dev_step(x_dev,y_dev)

				path = saver.save(sess,checkpoints_prefix,global_step=epoch_idx)
				print("Saved model checkpoint to {}\n".format(path))




































		

