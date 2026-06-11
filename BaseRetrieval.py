from abc import ABC, abstractmethod

class BaseRetrieval(ABC):

	def __init__(self, alpha):
		self.alpha =  alpha
	@abstractmethod
	def text_embedding(self, text):
		raise NotImplementedError

	@abstractmethod
	def image_embedding(self, text):
		raise NotImplementedError
