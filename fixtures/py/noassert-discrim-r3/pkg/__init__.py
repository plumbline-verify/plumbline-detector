from abc import ABC, abstractmethod


class Base(ABC):
    @abstractmethod
    def run(self): ...

    def __eq__(self, other):
        return False


class Concrete(Base):
    def run(self):
        return 1

    def __eq__(self, other):
        return isinstance(other, Concrete)
