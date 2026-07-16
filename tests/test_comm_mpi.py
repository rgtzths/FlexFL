import pytest

pytest.importorskip("mpi4py.MPI")

from unittest.mock import Mock, patch

from flexfl.comms.MPI import MPI


def test_recv_removes_dead_node():
    # Build the instance without __init__ (which needs the MPI runtime and a
    # size>1 communicator); drive recv() with a comm whose recv() returns None,
    # the graceful-death sentinel.
    inst = MPI.__new__(MPI)
    inst._nodes = {0, 1, 2}
    status = Mock()
    status.Get_source.return_value = 1
    inst.status = status
    comm = Mock()
    comm.recv.return_value = None
    inst.comm = comm

    with patch("flexfl.comms.MPI.Logger"):
        node_id, data = inst.recv()

    assert (node_id, data) == (1, None)
    assert 1 not in inst._nodes
