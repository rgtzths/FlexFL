

class RR:

    def __init__(self): 
        self.rr = set()


    def round_robin_single(self, workers: set) -> int:
        assert len(workers) > 0, "No workers available"
        workers_ =  workers - self.rr
        if len(workers_) == 0:
            self.rr = set()
            workers_ = workers
        workers_ = sorted(list(workers_))
        self.rr.add(workers_[0])
        return workers_[0]
        

    def round_robin_pool(self, size: int, workers: set) -> list[int]:
        assert len(workers) >= size, "Not enough workers available"
        chosen = []
        workers_ = workers - self.rr
        if len(workers_) < size:
            chosen = sorted(list(workers_))
            self.rr = set()
            
        for _ in range(size - len(chosen)):
            chosen.append(self.round_robin_single(workers))
        return chosen


workers = [1, 2, 3, 4, 5, 6, 7, 8]
rr = RR()

for _ in range(6):
    print(rr.round_robin_pool(3, set(workers)))
    # print(rr.rr)