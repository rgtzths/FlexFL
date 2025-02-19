import zenoh
import time
import sys

counter = 0

def main():
    zconf = zenoh.Config()
    session = zenoh.open(zconf)
    node_name = "test-node"

    try:
        node_name = sys.argv[1]
    except:
        ()



    def queryable_callback(query: zenoh.Query):
        global counter
        print(
            f">> [Queryable ] Received Query '{query.selector}'"
            + (
                f" with payload: {query.payload.to_string()}"
                if query.payload is not None
                else ""
            )
        )
        counter += 1
        query.reply(query.key_expr, f"work done {counter}")

    liveliness_token = session.liveliness().declare_token(f"fl_liveliness/{node_name}")
    session.declare_queryable(f"fl/{node_name}/work", queryable_callback)

    while True:
        time.sleep(1)


if __name__=='__main__':
    main()