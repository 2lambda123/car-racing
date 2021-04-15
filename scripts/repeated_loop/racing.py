import matplotlib.pyplot as plt
import pickle
import sympy as sp
import numpy as np
import sys
sys.path.append('src')
sys.path.append('src/utils')
import repeated_loop, base, racing_env


def racing(args):
    if args["simulation"]:
        track_spec = np.genfromtxt(
            "data/track_layout/ellipse.csv", delimiter=",")
        track_width = 1.0
        track = racing_env.ClosedTrack(track_spec, track_width)
        matrix_A = np.genfromtxt("data/sys/LTI/matrix_A.csv", delimiter=",")
        matrix_B = np.genfromtxt("data/sys/LTI/matrix_B.csv", delimiter=",")
        matrix_Q = np.diag([10.0, 0.0, 0.0, 0.0, 0.0, 10.0])
        matrix_R = np.diag([0.1, 0.1])
        # setup ego car
        ego = repeated_loop.DynamicBicycleModelRepeatedLoop(
            name="ego", param=base.CarParam(edgecolor="black"))
        ego.set_state_curvilinear(np.zeros((6,)))
        ego.set_state_global(np.zeros((6,)))
        ego.set_ctrl_policy(repeated_loop.MPCCBFRacingRepeatedLoop(
            matrix_A, matrix_B, matrix_Q, matrix_R, vt=0.8))
        ego.ctrl_policy.set_timestep(0.1)
        # setup surrounding cars
        t_symbol = sp.symbols("t")
        car1 = repeated_loop.NoDynamicsModelRepeatedLoop(
            name="car1", param=base.CarParam(edgecolor="orange"))
        car1.set_state_curvilinear_func(
            t_symbol, 0.2 * t_symbol + 4.0, 0.1 + 0.0 * t_symbol)
        car2 = repeated_loop.NoDynamicsModelRepeatedLoop(
            name="car2", param=base.CarParam(edgecolor="orange"))
        car2.set_state_curvilinear_func(
            t_symbol, 0.2 * t_symbol + 10.0, -0.1 + 0.0 * t_symbol)
        # setup simulation
        simulator = repeated_loop.CarRacingSimRepeatedLoop()
        simulator.set_timestep(0.1)
        simulator.set_track(track)
        simulator.add_vehicle(ego)
        ego.ctrl_policy.set_racing_sim(simulator)
        simulator.add_vehicle(car1)
        simulator.add_vehicle(car2)
        simulator.sim(sim_time=50.0)
        with open("data/simulator/racing.obj", "wb") as handle:
            pickle.dump(simulator, handle, protocol=pickle.HIGHEST_PROTOCOL)
    else:
        with open("data/simulator/racing.obj", "rb") as handle:
            simulator = pickle.load(handle)
    if args["plotting"]:
        simulator.plot_simulation()
        simulator.plot_state("ego")
    if args["animation"]:
        simulator.animate(filename="racing")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--simulation", action="store_true")
    parser.add_argument("--plotting", action="store_true")
    parser.add_argument("--animation", action="store_true")
    args = vars(parser.parse_args())
    racing(args)
