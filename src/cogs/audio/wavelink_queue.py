from wavelink import Queue, QueueEmpty


class WavelinkQueue(Queue):
    """
    Pops item at a given index from the queue
    """

    def pop_index(self, index):
        """
        Pops item from given index.
        Returns the item
        """
        if self.is_empty:
            raise QueueEmpty
        if index >= len(self):
            raise ValueError('No such index in queue')
        item = self[index]
        del self[index]
        return item
