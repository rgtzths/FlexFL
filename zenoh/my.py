import zenoh
import time


class Test:

    def __init__(self):
        self.zconf = zenoh.Config()
        self.session = zenoh.open(self.zconf)
        self.id = None
        self.total_nodes = 0
        self.nodes = set()
        self.determine_role()


    def handle_role(self, query: zenoh.Query):
        self.total_nodes += 1
        self.nodes.add(self.total_nodes)
        query.reply(query.key_expr, f"{self.total_nodes}")


    def determine_role(self):
        replies = self.session.get("fl/role")
        for r in replies:
            self.id = int(r.ok.payload.to_string())
        if self.id is None:
            self.id = 0
            self.session.declare_queryable("fl/role", self.handle_role)
            self.sub = self.session.declare_subscriber("fl/master")


    def send_work(self):
        self.recieved = {i: False for i in self.nodes}
        for i in self.nodes:
            self.session.put(f"fl/work/{i}", "work requested")
        print("Work requests sent")


    def recv_work(self, sample: zenoh.Sample):
        worker_id = int(sample.payload.to_string())
        self.recieved[worker_id] = True


    def handle_work(self, sample: zenoh.Sample):
        print("Received work request")
        time.sleep(self.id)
        self.session.put("fl/master", f"{self.id}")
        print("Work done")


    def handle_disconnect(self, sample: zenoh.Sample):
        if sample.kind == zenoh.SampleKind.PUT:
            return
        worker_id = int(f"{sample.key_expr}".split("/")[-1])
        self.nodes.remove(worker_id)
        print(f"Worker {worker_id} disconnected")


    def server(self):
        print("Running as server")
        self.sub = self.session.declare_subscriber("fl/master", self.recv_work)
        self.liveness_sub = self.session.liveliness().declare_subscriber("fl_liveliness/**", history=True, handler=self.handle_disconnect)
        while True:
            time.sleep(5)
            self.send_work()
            while not all(self.recieved.values()):
                time.sleep(0.5)
            print("All workers have completed their work")
            
    
    def worker(self):
        print(f"Running as worker {self.id}")
        self.sub = self.session.declare_subscriber(f"fl/work/{self.id}", self.handle_work)
        self.liveness_token = self.session.liveliness().declare_token(f"fl_liveliness/{self.id}")
        while True:
            time.sleep(10)


    def run(self):
        if self.id == 0:
            self.server()
        else:
            self.worker()


if __name__ == '__main__':
    test = Test()
    test.run()