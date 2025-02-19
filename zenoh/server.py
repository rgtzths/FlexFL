import zenoh
import time

def main():
    zconf = zenoh.Config()
    session = zenoh.open(zconf)
    nodes = set()  

    def liveliness_callback(sample : zenoh.Sample):
        print(f'Received liveliness on: {sample.key_expr} - kind: {sample.kind}')
        node_name = f"{sample.key_expr}".split("/")[-1]
        if sample.kind == zenoh.SampleKind.PUT:
            print(f'Adding node: {node_name}')
            nodes.add(node_name)
        else:
            print(f'removing node: {node_name}')
            nodes.remove(node_name)

    liveliness_sub = session.liveliness().declare_subscriber("fl_liveliness/**", history=True, handler=liveliness_callback)


    while True:
        time.sleep(5)

        for n in nodes:
            replies = session.get(f"fl/{n}/work")
            for reply in replies:
                print(f">> Received ('{reply.ok.key_expr}': '{reply.ok.payload.to_string()}')")




if __name__=='__main__':
    main()