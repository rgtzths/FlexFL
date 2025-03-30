from flexfl.comms.Zenoh import Zenoh

if __name__ == "__main__":
    import sys
    z = Zenoh(
        ip="localhost",
        zenoh_port=7447,
        is_anchor= len(sys.argv) <= 1,
    )
    print(z.id)

    if z.id == 0:
        node_id, data = z.recv()
        print(f"Received data from node {node_id}: {data}")
        z.send(node_id, b"Hello from master!")
    else:
        z.send(0, b"Hello from slave!")
        node_id, data = z.recv()
        print(f"Received data from node {node_id}: {data}")
    z.close()
