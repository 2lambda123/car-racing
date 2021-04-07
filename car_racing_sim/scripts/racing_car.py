import numpy as np
import sympy as sp
import vehicle_dynamics
import rospy
from car_racing_dev.msg import VehicleControl


class BicycleDynamicsParam:
    def __init__(
        self,
        m=1.98,
        lf=0.125,
        lr=0.125,
        Iz=0.024,
        Df=0.8 * 1.98 * 9.81 / 2.0,
        Cf=1.25,
        Bf=1.0,
        Dr=0.8 * 1.98 * 9.81 / 2.0,
        Cr=1.25,
        Br=1.0,
    ):
        self.m = m
        self.lf = lf
        self.lr = lr
        self.Iz = Iz
        self.Df = Df
        self.Cf = Cf
        self.Bf = Bf
        self.Dr = Dr
        self.Cr = Cr
        self.Br = Br

    def get_params(self):
        return self.m, self.lf, self.lr, self.Iz, self.Df, self.Cf, self.Bf, self.Dr, self.Cr, self.Br


class CarParam:
    def __init__(self, length=0.4, width=0.2, facecolor="None", edgecolor="black"):
        self.length = length
        self.width = width
        self.facecolor = facecolor
        self.edgecolor = edgecolor
        self.dynamics_param = BicycleDynamicsParam()


class BaseModel:
    def __init__(self, name=None, param=None):
        self.name = name
        self.param = param
        self.no_dynamics = False
        self.xdim = 6
        self.udim = 2
        self.time = 0.0
        self.timestep = None
        self.xcurv = None
        self.xglob = None
        self.u = None
        self.closedloop_time = []
        self.closedloop_xcurv = []
        self.closedloop_xglob = []
        self.closedloop_u = []

    def set_timestep(self, dt):
        self.timestep = dt

    def set_state_curvilinear(self, xcurv):
        self.xcurv = xcurv

    def set_state_global(self, xglob):
        self.xglob = xglob

    def set_track(self, track):
        self.track = track

    def set_ctrl_policy(self, ctrl_policy):
        self.ctrl_policy = ctrl_policy
        self.ctrl_policy.agent_name = self.name

    def calc_ctrl_input(self):
        self.ctrl_policy.set_state(self.xcurv)
        self.ctrl_policy.calc_input()
        self.u = self.ctrl_policy.get_input()

    def forward_dynamics(self):
        pass

    def forward_one_step(self):
        if self.no_dynamics:
            self.forward_dynamics()
            self.update_memory()
        else:
            self.calc_ctrl_input()
            self.forward_dynamics()
            self.update_memory()

    def update_memory(self):
        self.closedloop_time.append(self.time)
        self.closedloop_xcurv.append(self.xcurv)
        self.closedloop_xglob.append(self.xglob)
        self.closedloop_u.append(self.u)


class RealtimeBaseModel:
    def __init__(self):
        self.__sub_input = None
        self.__pub_state = None

    def __input_cb(self, msg):
        self.u[1] = msg.acc
        self.u[0] = msg.delta

    def set_subscriber(self):
        self.__sub_input = rospy.Subscriber("vehicle1/input", VehicleControl, self.__input_cb)


class NoPolicyModel(BaseModel):
    def __init__(self, name=None, param=None, xcurv=None, xglob=None):
        BaseModel.__init__(self, name=name, param=param)
        self.no_dynamics = True

    def set_state_curvilinear_func(self, t_symbol, s_func, ey_func):
        self.t_symbol = t_symbol
        self.s_func = s_func
        self.ey_func = ey_func

    def get_estimation(self, t0):
        # position estimation in curvilinear coordinates
        xcurv_est = np.zeros(self.xdim)
        xcurv_est[0] = sp.diff(self.s_func, self.t_symbol).subs(self.t_symbol, t0)
        xcurv_est[1] = sp.diff(self.ey_func, self.t_symbol).subs(self.t_symbol, t0)
        xcurv_est[2] = 0
        xcurv_est[3] = 0
        xcurv_est[4] = self.s_func.subs(self.t_symbol, t0)
        xcurv_est[5] = self.ey_func.subs(self.t_symbol, t0)
        # position estimation in global coordinates
        X, Y = self.track.get_global_position(xcurv_est[4], xcurv_est[5])
        psi = self.track.get_orientation(xcurv_est[4], xcurv_est[5])
        xglob_est = np.zeros(self.xdim)
        xglob_est[0:3] = xcurv_est[0:3]
        xglob_est[3] = psi
        xglob_est[4] = X
        xglob_est[5] = Y
        return xcurv_est, xglob_est

    def get_trajectory_nsteps(self, t0, delta_t, n):
        xcurv_est_nsteps = np.zeros((self.xdim, n))
        xglob_est_nsteps = np.zeros((self.xdim, n))
        for index in range(n):
            xcurv_est, xglob_est = self.get_estimation(self.time + index * delta_t)
            xcurv_est_nsteps[:, index] = xcurv_est
            xglob_est_nsteps[:, index] = xglob_est
        return xcurv_est_nsteps, xglob_est_nsteps

    def forward_dynamics(self):
        self.time += self.timestep
        self.xcurv, self.xglob = self.get_estimation(self.time)


class DynamicBicycleModel(BaseModel):
    def __init__(self, name=None, param=None, xcurv=None, xglob=None):
        BaseModel.__init__(self, name=name, param=param)

    def forward_dynamics(self):
        # This function computes the system evolution. Note that the discretization is delta_t and therefore is needed that
        # dt <= delta_t and ( dt / delta_t) = integer value

        # Discretization Parameters
        delta_t = 0.001
        xglob_next = np.zeros(self.xdim)
        xcurv_next = np.zeros(self.xdim)
        xglob_next = self.xglob
        xcurv_next = self.xcurv
        Param = CarParam()
        # Initialize counter
        i = 0
        while (i + 1) * delta_t <= self.timestep:
            s = xcurv_next[4]
            curv = self.track.get_curvature(s)
            xglob_next, xcurv_next = vehicle_dynamics.vehicle_dynamics(
                Param.dynamics_param, curv, xglob_next, xcurv_next, delta_t, self.u
            )
            if s < 0:
                pass
                # Don't need this checker as curvature can be calculated even s < 0
                # print("Start Point: ", self.x, " Input: ", self.ctrl_policy.u)
                # print("x_next: ", x_next)
            # Increment counter
            i = i + 1
        # Noises
        noise_vx = np.maximum(-0.05, np.minimum(np.random.randn() * 0.01, 0.05))
        noise_vy = np.maximum(-0.1, np.minimum(np.random.randn() * 0.01, 0.1))
        noise_wz = np.maximum(-0.05, np.minimum(np.random.randn() * 0.005, 0.05))

        xcurv_next[0] = xcurv_next[0] + 0.1 * noise_vx
        xcurv_next[1] = xcurv_next[1] + 0.1 * noise_vy
        xcurv_next[2] = xcurv_next[2] + 0.1 * noise_wz

        self.xcurv = xcurv_next
        self.xglob = xglob_next
        self.time += self.timestep


class RealtimeDynamicBicycleModel(DynamicBicycleModel, RealtimeBaseModel):
    def __init__(self, name=None, param=None, xcurv=None, xglob=None):
        DynamicBicycleModel.__init__(self, name=name, param=param)
        RealtimeBaseModel.__init__(self)
