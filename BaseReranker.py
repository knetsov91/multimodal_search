from abc import ABC, abstractmethod

class BaseReranker(ABC):

    @abstractmethod
    def rerank(self, results,  search_image_data, search_text):
        raise NotImplementedError