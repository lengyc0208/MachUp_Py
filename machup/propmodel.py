import numpy as np
from scipy.interpolate import interp1d
from scipy.integrate import simps, ode
import math as m
import matplotlib.pyplot as plt
from scipy import optimize as opt


class PropModel:
    """Descritizes prop geometry information and performs blade element theory analysis.
       
    Parameters
    ----------
    machup.Plane.Prop
        Prop object that contains all of the necessary information
        about propeller geometry.

    Returns
    -------
    PropGrid
        The newly created PropModel object.

    """
    def __init__(self, prop, cg_location,units,wing_points = None):
        self._prop = prop
        self._name = prop.name
        self._position = prop.get_position()
        self._calc_spacing()
        self._calc_orientation()
        self._calc_coefficients()
        self._calc_pitch()
        self._calc_chord()
        self._calc_motor()
        self._calc_stall_delay()
        if wing_points is not None:
            self._calc_immersed_wing_points(wing_points)
            self._wing_points = wing_points
        self._init_speed_vars()
        self._set_slipstream_variables()
        self._cg_location = cg_location
        self._units = units

    #---------------------------------------Functions for setting up variables based on geometry-----------------------------------------

    def _calc_spacing(self):
        self._d = self._prop.get_diameter()
        hd = self._prop.get_hub_diameter()
        self._nodes = self._prop.get_number_of_nodes()
        self._zeta = np.linspace(hd/self._d,0.999,self._nodes)
        self._r = self._zeta*self._d*0.5

    def _calc_orientation(self):
        self._theta,self._gamma = np.radians(self._prop.get_orientation())
        st = m.sin(self._theta)
        ct = m.cos(self._theta)
        sg = m.sin(self._gamma)
        cg = m.cos(self._gamma)
        self._prop_forward = np.array([ct*cg,ct*sg,-st])
        self._rot_dir = self._prop.get_rot_dir()

        self._slip_dir = -self._prop_forward#indicates direction the slipstream travels. Will be altered later to include slipstream deflection due to high incidence angles

    def _calc_coefficients(self):
        '''
        r_airfoil, t_airfoil = self._prop.get_airfoils()
        self._alpha_L0 = self._linearInterp(r_airfoil.get_zero_lift_alpha(),t_airfoil.get_zero_lift_alpha(),self._zeta)
        self._CL_alpha = self._linearInterp(r_airfoil.get_lift_slope(),t_airfoil.get_lift_slope(),self._zeta)
        self._CL_max = self._linearInterp(r_airfoil.get_max_lift(),t_airfoil.get_max_lift(),self._zeta)
        self._a_stall = self._CL_max/self._CL_alpha

        rCD0,rCDL,rCDL2 = r_airfoil.get_drag_coefficients()
        tCD0,tCDL,tCDL2 = t_airfoil.get_drag_coefficients()
        self._CD_0 = self._linearInterp(rCD0,tCD0,self._zeta)
        self._CD_L = self._linearInterp(rCDL,tCDL,self._zeta)
        self._CD_L2 = self._linearInterp(rCDL2,tCDL2,self._zeta)
        '''

        airfoils = self._prop.get_airfoils()
        if len(airfoils) == 0:
            self._prop.airfoil()

        if len(airfoils) == 1:
            af = list(airfoils.values())[0]
            span_ordered_list = [(None,af)]
            self._alpha_L0 = np.full_like(self._zeta,af.get_zero_lift_alpha())
            self._CL_alpha = np.full_like(self._zeta,af.get_lift_slope())
            self._CL_max = np.full_like(self._zeta,af.get_max_lift())
            self._a_stall = self._CL_max/self._CL_alpha

            CD0,CDL,CDL2 = af.get_drag_coefficients()
            self._CD_0 = np.full_like(self._zeta, CD0)
            self._CD_L = np.full_like(self._zeta, CDL)
            self._CD_L2 = np.full_like(self._zeta, CDL2)

        if len(airfoils) > 1:
            #raise RuntimeError("Multiple airfoils not yet supported")
            span_wise_list = []

            for af in list(airfoils.values()):
                span_pos = af.get_span_position()
                if span_pos == None:
                    raise RuntimeError("If multiple airfoils are provided, span_position must also be specified")
                elif span_pos == "root" or span_pos == "Root" or span_pos == "ROOT":
                    span_pos = self._zeta[0]
                elif span_pos == "tip" or span_pos == "Tip" or span_pos == "TIP":
                    span_pos = self._zeta[-1]

                af_tuple = (span_pos,af)
                span_wise_list.append(af_tuple)

            span_ordered_list = sorted(span_wise_list)
            loc = []
            aL0 = []
            CLa = []
            CLm = []
            CD0 = []
            CD1 = []
            CD2 = []
            for airfoil in span_ordered_list:
                loc.append(airfoil[0])
                af = airfoil[1]
                aL0.append(af.get_zero_lift_alpha())
                CLa.append(af.get_lift_slope())
                CLm.append(af.get_max_lift())
                CD_0,CD_L,CD_L2 = af.get_drag_coefficients()
                CD0.append(CD_0)
                CD1.append(CD_L)
                CD2.append(CD_L2)
            loc = np.array(loc)
            aL0 = np.array(aL0)
            CLa = np.array(CLa)
            CLm = np.array(CLm)
            CD0 = np.array(CD0)
            CD1 = np.array(CD1)
            CD2 = np.array(CD2)

            '''
            if len(airfoils) == 2:
                inter_kind = "linear"
            elif len(airfoils) == 3:
                inter_kind = "quadratic"
            elif len(airfoils) > 3:
                inter_kind = "cubic"
            '''

            inter_kind = 'linear'
            aL0_fun = interp1d(loc,aL0,kind=inter_kind,bounds_error = False,fill_value = (aL0[0],aL0[-1]))
            CLa_fun = interp1d(loc,CLa,kind=inter_kind,bounds_error = False,fill_value = (CLa[0],CLa[-1]))
            CLm_fun = interp1d(loc,CLm,kind=inter_kind,bounds_error = False,fill_value = (CLm[0],CLm[-1]))
            CD0_fun = interp1d(loc,CD0,kind=inter_kind,bounds_error = False,fill_value = (CD0[0],CD0[-1]))
            CD1_fun = interp1d(loc,CD1,kind=inter_kind,bounds_error = False,fill_value = (CD1[0],CD1[-1]))
            CD2_fun = interp1d(loc,CD2,kind=inter_kind,bounds_error = False,fill_value = (CD2[0],CD2[-1]))

            self._alpha_L0 = aL0_fun(self._zeta)
            self._CL_alpha = CLa_fun(self._zeta)
            self._CL_max = CLm_fun(self._zeta)
            self._a_stall = self._CL_max/self._CL_alpha
            self._CD_0 = CD0_fun(self._zeta)
            self._CD_L = CD1_fun(self._zeta)
            self._CD_L2 = CD2_fun(self._zeta)
            
        self._airfoil_span_list = span_ordered_list

    def _calc_pitch(self):
        pitch_info = self._prop.get_pitch_info()
        pitch_increment = pitch_info.get("pitch_increment",None)
        if pitch_info["type"] == "default":
            Kc = 0.5
        #for propeller info imported from file, pitch should be
        #given as degrees at radial positions r/R
        elif pitch_info["type"] == "from_file":
            filename = pitch_info["filename"]
            r,p = self._import_data(filename)
            p = np.radians(p)
            pitch_func = interp1d(r,p,kind='cubic',fill_value = "extrapolate")

            beta_c = pitch_func(self._zeta)
            l_c = 2*np.pi*self._r*np.tan(beta_c)
            l = (2*np.pi*self._r)*(l_c-2*np.pi*self._r*np.tan(self._alpha_L0))/(2*np.pi*self._r+l_c*np.tan(self._alpha_L0))
            self._beta = np.arctan(l/(2*np.pi*self._r))
            if pitch_increment:
                self._beta+=np.radians(pitch_increment)
            return
        elif pitch_info["type"] == "ratio":
            Kc = pitch_info["value"]
        elif pitch_info["type"] == "value":
            Kc = pitch_info["value"]/self._d
        else:
            raise RuntimeError("Invalid pitch type")
        
        # convert chord line pitch (Kc) to aerodynamic pitch (K)
        K = np.pi*self._zeta*((Kc-np.pi*self._zeta*np.tan(self._alpha_L0))/(np.pi*self._zeta+Kc*np.tan(self._alpha_L0)))
        self._beta = np.arctan2(K,np.pi*self._zeta)
        if pitch_increment:
            self._beta+=np.radians(pitch_increment)

    def _calc_chord(self):
        chord_info = self._prop.get_chord_info()
        
        if chord_info["type"] == "default":
            self._cb = 0.075*self._d*np.sqrt(1-self._zeta**2)

        #for propeller info imported from file, chord length should be
        #given as c/R at radial positions r/R
        elif chord_info["type"] == "from_file":
            filename = chord_info["filename"]
            r,c = self._import_data(filename)
            chord_func = interp1d(r,c,kind='cubic',fill_value = "extrapolate")
            self._cb = chord_func(self._zeta)*self._d/2.

        elif chord_info["type"] == "linear":
            root = chord_info["root"]
            tip = chord_info.get("tip",root)
            self._cb = self._linearInterp(root,tip,self._zeta)

        elif chord_info["type"] == "elliptical":
            self._cb = chord_info["root"]*np.sqrt(1-self._zeta**2)
        else:
            raise RuntimeError("Invalid chord type")

        self._k = self._prop.get_num_of_blades()
        self._chatb = (self._k*self._cb)/self._d
        self._c_r = self._cb/self._r



    def _calc_motor(self):
        motor_info = self._prop.get_motor_info()
        self._has_motor = motor_info.get("has_motor",False)
        if self._has_motor:
            self._Kv = motor_info["motor_kv"]
            self._Rm = motor_info["motor_resistance"]
            self._Io = motor_info["motor_no_load_current"]
            self._Gr = motor_info["gear_reduction"]
            self._Rb = motor_info["battery_resistance"]
            self._Eo = motor_info["battery_voltage"]
            self._Rc = motor_info["speed_control_resistance"]

    def _calc_stall_delay(self):

        #Corrigan stall alpha shift
        c_r = self._c_r
        K = (0.1517/c_r)**(1/1.084)
        sep = K*c_r/0.136
        n=1
        self._dA = self._a_stall*((sep**n)-1)


        #Viterna's Method Constants
        #have to set up differenct constants for positive and negative angles of attack
        #negative angles of attack are treated as positive angles that stall sooner, and then flipped to be negative
        self._a_stall_neg = self._a_stall+1.5*self._alpha_L0 #approximation for negative stall point. symmetric airfoils have equal stall on both sides.
        self._CL_max_neg = self._a_stall_neg*self._CL_alpha

        #modified CD at delayed stall
        self._delay_a_stall = self._a_stall+self._dA
        self._delay_a_stall_neg = -self._a_stall+self._dA
        sd_CL = self._delay_a_stall*self._CL_alpha
        sd_CL_neg = self._delay_a_stall_neg*self._CL_alpha

        self._CD_max = self._CD_0 + self._CD_L*sd_CL + self._CD_L2*sd_CL*sd_CL
        self._CD_max_neg = self._CD_0 + self._CD_L*sd_CL_neg + self._CD_L2*sd_CL_neg*sd_CL_neg

        CDm = 1.11+0.018*10
        sas = np.sin(self._a_stall)
        cas = np.cos(self._a_stall)
        sasn = np.sin(self._a_stall_neg)
        casn = np.cos(self._a_stall_neg)

        sdas = np.sin(self._delay_a_stall)
        cdas = np.cos(self._delay_a_stall)
        sdasn = np.sin(-self._delay_a_stall_neg)
        cdasn = np.cos(-self._delay_a_stall_neg)

        self._A1 = CDm/2
        self._B1 = CDm
        self._A2 = (self._CL_max-CDm*sas*cas)*sas/(cas*cas)
        self._B2 = (self._CD_max-CDm*sdas*sdas)/cdas

        self._A2_neg = (self._CL_max_neg-CDm*sasn*casn)*sasn/(casn*casn)
        self._B2_neg = (self._CD_max_neg-CDm*sdasn*sdasn)/cdasn

    def _calc_immersed_wing_points(self, wing_points):
        #determine which control points fall in cylinder behind prop and their respective distances along the streamtube and from the center of the streamtube
        prop_pos = self._position
        self._t = np.dot((wing_points-prop_pos),self._prop_forward)#distance down centerline to position of min distance to point. negative is behind prop, positive is in front of prop
        stream_vec = self._prop_forward*self._t[:, np.newaxis] #vector down centerline to position of min distance to point
        P = prop_pos+stream_vec #position on center line of min distance to point
        center2point_vec = wing_points-P #vector from point to centerline
        self._center2point_dist = self._vec_mag_mult(center2point_vec) #distance from point to center line
        tangent = np.cross(self._prop_forward,center2point_vec)
        self._tangent_norm = tangent/self._vec_mag_mult(tangent)[:,None]

        self._points_in_stream = np.where((abs(self._center2point_dist)<=(self._d/2))&(self._t<0.))

    def _init_speed_vars(self):
        self._ei = np.zeros(self._nodes)
        self._rot_per_sec = 15

    def _set_slipstream_variables(self):
        self._thetaFF = np.arccos(-self._zeta)#theta transform for fourier fit
        self._bg = 0.114 #stagnant gaussian profile expansion rate
        self._current_fit = False
        self._bgx = np.tan(np.radians(4.8))/np.sqrt(-np.log(0.5))
        self._tang_profile_width_ratio = 1.5
        self._tang_profile_max_ratio = 0.25


    #---------------------------------------Functions for setting prop operating state-----------------------------------------
    def _set_aero_state(self, aero_state):
        if aero_state:
            a = m.radians(aero_state.get("alpha",0.))
            b = m.radians(aero_state.get("beta",0.))
            ca = m.cos(a)
            sa = m.sin(a)
            cb = m.cos(b)
            sb = m.sin(b)
            v_xyz = np.zeros(3)
            v_xyz[:] = 1/m.sqrt(1.-sa*sa*sb*sb)
            v_xyz[0] *= -ca*cb
            v_xyz[1] *= -ca*sb
            v_xyz[2] *= -sa*cb
            self._v_xyz = v_xyz

            if "V_mag" not in aero_state:
                raise RuntimeError("Must supply 'V_mag' key and value")
            if "rho" not in aero_state:
                raise RuntimeError("Must supply 'rho' key and value")

            self._rho = aero_state["rho"]
            self._Vinf = aero_state["V_mag"]
        else:
            print("'aero_state' not provided. Using default values: V=10 ft/s, rho = 0.0023769 slugs/ft^3")
            self._rho = 0.0023769
            self._Vinf = 10
            self._v_xyz = np.array([-1,0,0])

        self._Vs = np.dot(self._v_xyz*self._Vinf, self._slip_dir)#component of freestream in direction of slipstream

    def _set_prop_state(self, prop_state):
        if prop_state:
            self._solve_from_power = False
            self._solve_from_motor = False
            if "J" in prop_state:
                self._J = prop_state["J"]
                if self._J == 0. or self._Vinf == 0.:
                    if "rot_per_sec" in prop_state:
                        self._rot_per_sec = prop_state["rot_per_sec"]
                    else:
                        raise RuntimeError("For advance ratio of zero, must also supply 'rot_per_sec' key and value")
                else:
                    self._rot_per_sec = self._Vinf/(self._d*self._J)
            elif "rot_per_sec" in prop_state:
                self._rot_per_sec = prop_state["rot_per_sec"]
                self._J = self._Vinf/(self._rot_per_sec*self._d)
            elif "brake_power" in prop_state:
                self._brake_power = prop_state["brake_power"]
                self._solve_from_power = True
            elif "electric_throttle" in prop_state:
                self._throttle = prop_state["electric_throttle"]
                self._solve_from_power = True
                self._solve_from_motor = True

                
            else:
                raise RuntimeError("Must supply 'J', 'rot_per_sec', or 'brake_power' key and value")
        else:
            #print("'prop_state' not provided. Using default values: J=0.5")
            self._J = 0.5
            self._rot_per_sec = self._Vinf/(self._d*self._J)
            self._solve_from_power = False
            self._solve_from_motor = False

    #---------------------------------------Functions for calculating prop performance-----------------------------------------

    def _find_coefficients(self):
        self._einf = np.arctan2(self._J, (m.pi*self._zeta))

        
        #initial guess for iterative solution of ei if not previously solved
        if not np.any(self._ei):
            self._ei = self._beta-self._einf

        #set constant values for ei solver
        self._ei_func_a = (self._chatb/(8*self._zeta))
        self._ei_func_b = np.arccos(np.exp(-(self._k*(1-self._zeta))/(2*np.sin(self._beta[-1]))))

        #solve for ei
        self._ei = self._find_ei()
        self._alpha = self._beta-self._einf-self._ei

        CLift,CLift_a,CDrag = self.get_coefficients_alpha(self._alpha)	
        self._CL = CLift
        self._CD = CDrag


        cei = np.cos(self._ei)
        ceinf = np.cos(self._einf)
        cee = np.cos(self._einf+self._ei)
        see = np.sin(self._einf+self._ei)
        teinf = np.tan(self._einf)

        z2 = self._zeta*self._zeta
        z3 = z2*self._zeta
        cei2 = cei*cei
        ceinf2 = ceinf*ceinf
        teinf2 = teinf*teinf
        pi2 = m.pi*m.pi

        CT_z = z2*self._chatb*((cei2)/(ceinf2))*(CLift*cee-CDrag*see)
        Cl_z = z3*self._chatb*((cei2)/(ceinf2))*(CDrag*cee+CLift*see)
        CN_z = (z2)*self._chatb*(cei2)*(2*teinf*(CDrag*cee+CLift*see)-(teinf2)*(CLift*cee-(CLift_a+CDrag)*see))
        Cn_z = (z3)*self._chatb*(cei2)*(2*teinf*(CLift*cee-CDrag*see)+(teinf2)*((CLift_a+CDrag)*cee+CLift*see))

        self._CT = ((pi2)/4)*simps(CT_z,self._zeta)
        self._Cl = ((pi2)/8)*simps(Cl_z,self._zeta)
        self._CN_a = ((pi2)/8)*simps(CN_z,self._zeta)
        self._Cn_a = ((pi2)/16)*simps(Cn_z,self._zeta)

        self._CP = self._Cl*2*m.pi

        self._efficiency = (self._CT*self._J)/self._CP
        if self._CT<=0.:
            self._efficiency = 0.

    def _find_ei(self,error = 1E-11):

        x0 = np.copy(self._ei)
        x1 = np.copy(x0)*(1+1e-4)-1e-4
        y0 = self._ei_function(x0)
        y1 = self._ei_function(x1)

        x2 = np.copy(x0)
        i = 0
        while True:
            loc = np.where(abs(y1-y0)>error)
            x2[loc] = x1[loc]-((y1[loc]*(x1[loc]-x0[loc]))/(y1[loc]-y0[loc]))
            i+=1
            x2 = self._correct_ei(x2)
            if i>50 and loc[0].size<3:
                #print("Ei convergence issues @ J=",self._J)
                return x2
            if loc[0].size == 0:
                return x2

            x0 = np.copy(x1)
            x1 = np.copy(x2)
            y0 = np.copy(y1)
            y1 = self._ei_function(x1)


    def _ei_function(self,ei):
        alpha = self._beta-self._einf-ei
        CLift = self._get_CL(alpha)
        zero = (self._ei_func_a*CLift)-self._ei_func_b*np.tan(ei)*np.sin(self._einf+ei)
        return zero


    def _correct_ei(self,ei):
        correct_sign = np.sign(self._beta-self._einf)
        ei = np.where(np.absolute(ei)<1.,ei,0.3*correct_sign)
        ei = np.where(np.sign(ei) != correct_sign, ei*-1, ei)
        return ei


    #--------------------Functions for finding prop_state based on input power------------------------
    def _prop_state_from_power(self):
        if self._solve_from_motor:
            if self._has_motor:
                self._rot_per_sec = self._find_rot_rate_motor()
            else:
                raise RuntimeError("Propeller does not have electric motor information")
        else:
            self._rot_per_sec = self._find_rot_rate_power()
        self._J = self._Vinf/(self._rot_per_sec*self._d)

    def _find_rot_rate_power(self, error = 1E-14):
        x0 = self._rot_per_sec #get a better guess
        x1 = x0*1.5
        y0 = self._zero_power_difference(x0)
        if abs(y0)<error:
            return x0
        y1 = self._zero_power_difference(x1)
        while True:
            #new guess based on secant method
            x2 = x1-((y1*(x1-x0))/(y1-y0))
            #if solution has converged, return results
            if abs(x2-x1)<error:
                return x2
            #set variables for next iteration
            x0=x1
            y0=y1
            x1=x2
            y1=self._zero_power_difference(x1)

    def _zero_power_difference(self,rot_per_sec_est):
        self._rot_per_sec = rot_per_sec_est
        self._J = self._Vinf/(self._rot_per_sec*self._d)
        self._find_coefficients()
        prop_power = (self._rho*(self._rot_per_sec**3)*(self._d**5)*self._CP)
        return prop_power-self._brake_power

    def _find_rot_rate_motor(self,error = 1E-14):
        x0 = self._rot_per_sec #get a better guess
        x1 = x0*1.5
        y0 = self._zero_torque_difference(x0)
        if abs(y0)<error:
            return x0
        y1 = self._zero_torque_difference(x1)
        while True:
            #new guess based on secant method
            x2 = x1-((y1*(x1-x0))/(y1-y0))
            #if solution has converged, return results
            if abs(x2-x1)<error:
                return x2
            #set variables for next iteration
            x0=x1
            y0=y1
            x1=x2
            y1=self._zero_torque_difference(x1)

    def _zero_torque_difference(self,rot_per_sec_est):
        self._rot_per_sec = rot_per_sec_est
        self._J = self._Vinf/(self._rot_per_sec*self._d)
        self._find_coefficients()
        prop_torque = (self._rho*(self._rot_per_sec**2)*(self._d**5)*self._Cl)
        motor_torque = self._electric_motor_torque()
        return prop_torque-motor_torque

    def _electric_motor_torque(self):
        N = self._rot_per_sec*60
        ns = 1-0.079*(1-self._throttle)
        Im = (ns*self._throttle*self._Eo-(self._Gr/self._Kv)*N)/(ns*self._throttle*self._Rb+self._Rc+self._Rm)
        Tq = (7.0432*self._Gr/self._Kv)*(Im-self._Io)
        if self._units == None:
            raise RuntimeError("Units must be provided for electric motor analysis. Please specify units as either 'English' or 'SI'")
        if self._units == "English":
            return Tq
        else: 
            return Tq*1.3558179483314

    #---------------------------------------Functions for calculating prop forces-----------------------------------------

    def _calc_forces(self):
        if self._solve_from_power == True:
            self._prop_state_from_power()
        else:
            self._find_coefficients()

        self._find_Vi()

        angle = self._vec_angle(self._prop_forward,-self._v_xyz)
        if angle == 0.:
            N,n=0.,0.
            N_vec = np.zeros(3)
        else:
            N = self._rho*(self._rot_per_sec*self._rot_per_sec)*(self._d**4)*self._CN_a*angle
            n = self._rho*(self._rot_per_sec*self._rot_per_sec)*(self._d**5)*self._Cn_a*angle
            N_dir = np.cross(np.cross(-self._v_xyz, self._prop_forward),self._prop_forward)
            N_vec = N_dir/m.sqrt(N_dir[0]**2+N_dir[1]**2+N_dir[2]**2)

        self._T = self._rho*(self._rot_per_sec*self._rot_per_sec)*(self._d**4)*self._CT
        self._l = self._rho*(self._rot_per_sec*self._rot_per_sec)*(self._d**5)*self._Cl*(-self._rot_dir)
        self._F = (self._T*self._prop_forward)+(N*N_vec)
        x,y,z = self._position-self._cg_location
        thrust_offset_M = np.array([self._F[2]*y-self._F[1]*z,
                                    self._F[0]*z-self._F[2]*x,
                                    self._F[1]*x-self._F[0]*y])
        self._M = thrust_offset_M+(self._rot_dir*n*N_vec)+self._l*self._prop_forward
        return self._F, self._M,self._T,self._l


    #--------------------------------------Functions for prepping Goates Slipstream Model-----------------------

    def _find_Vi(self):
        self._Vi = self._rot_per_sec*2*m.pi*self._r*np.sin(self._ei)/np.cos(self._einf)
        eb = self._ei+self._einf
        self._Vxi = self._Vi*np.cos(eb)
        self._Vti = self._Vi*np.sin(eb)
        self._Vxi_fun = interp1d(self._r,self._Vxi,bounds_error = False, fill_value = (0,0))
        self._Vti_fun = interp1d(self._r,self._Vti,bounds_error = False, fill_value = (0,0))
        self._current_fit = False


    def _find_VxFF(self):
        AnBn = np.zeros(6)
        opt_result = opt.minimize(self._fit_error,AnBn,(self._Vxi))
        AnBn = opt_result.x
        VxFF = self._fourier(AnBn)
        VxiFF_fun = interp1d(self._r,VxFF,bounds_error = False, fill_value = 0)

        AnBn.fill(0)
        opt_result = opt.minimize(self._fit_error,AnBn,(self._Vti))
        AnBn = opt_result.x
        VtFF = self._fourier(AnBn)
        VtiFF_fun = interp1d(self._r,VtFF,bounds_error = False, fill_value = 0)
        return VxiFF_fun,VtiFF_fun

    def _fourier(self,AnBn):
        theta = self._thetaFF
        fit = np.zeros_like(theta)
        half_size = int(AnBn.size/2)
        for i in range(half_size):
            fit+=AnBn[i]*np.sin((i+1)*theta)+AnBn[half_size+i]*np.cos((i+1)*theta)
            #fit+=AnBn[i]*np.sin((i+1)*np.pi*self._zeta)+AnBn[half_size+i]*np.cos((i+1)*np.pi*self._zeta)
        return fit

    def _fit_error(self,AnBn,V):
        fit = self._fourier(AnBn)
        square = (V-fit)**2
        RMS = np.sqrt(np.mean(square))
        return RMS

    #---------------------------------------Functions for calculating prop slipstream effects on wing points-----------------------------------------
    def _calc_prop_wing_vel(self):
        wing_points = self._wing_points
        Vx_mag, Vt_mag = self._stone_slipstream(self._points_in_stream)

        tangential_vel = np.zeros_like(wing_points)
        axial_vel = np.zeros_like(wing_points)
        tangential_vel[self._points_in_stream] = self._tangent_norm[self._points_in_stream]*Vt_mag[:,None]
        axial_vel[self._points_in_stream] = self._slip_dir*Vx_mag[:,None]
        total_vel = tangential_vel+axial_vel
        return total_vel

    def _stone_slipstream(self,loc):
        s = -self._t[loc]
        Vxi,Vti = self._Vxi,self._Vti
        if s.size == 0:
            return s,s

        R = self._d/2
        kd = 1+(s/np.sqrt((s*s)+(R*R)))

        r_prime = np.empty([self._r.size,s.size])
        r_prime[0] = self._r[0] #nacelle radius, assume it is constant with hub radius for now

        Vx2 = Vxi[1:,None]+Vxi[0:-1,None]
        Kv = (2*self._Vinf+Vx2)/(2*self._Vinf+kd[None,:]*Vx2)
        for i in range(1,self._r.size):
            r_prime[i] = np.sqrt((r_prime[i-1]*r_prime[i-1])+((self._r[i]*self._r[i])-(self._r[i-1]*self._r[i-1]))*Kv[i-1])

        Vxim = Vxi[:,None]*kd
        Vtim = np.empty_like(Vxim)
        Vtim[int(self._r.size/10):][:] = 2*Vti[int(self._r.size/10):,None]*self._r[int(self._r.size/10):,None]/r_prime[int(self._r.size/10):][:]
        Vtim[0:int(self._r.size/10)][:] = (Vtim[int(self._r.size/10)][:]/r_prime[int(self._r.size/10)][:])*r_prime[0:int(self._r.size/10)][:]

        Vx_point = np.empty_like(s)
        Vt_point = np.empty_like(s)

        in_straight_tube = self._center2point_dist[loc]

        for i in range(0,s.size):
            Vx_point[i] = np.interp(in_straight_tube[i],r_prime[:,i],Vxim[:,i], left=0,right=0)
            Vt_point[i] = np.interp(in_straight_tube[i],r_prime[:,i],Vtim[:,i], left=0,right=0)*self._rot_dir

        return Vx_point, Vt_point

    #----------------------------Functions for calculating prop induced velocity at arbitrary control points-----------------------------

    def _find_propwash_velocities(self, control_points):#Stone's method
        #determine which control points fall in cylinder behind prop and their respective distances along the streamtube and from the center of the streamtube
        pos = self._position
        centerline_dist = np.dot((control_points-pos),self._prop_forward)#distance down centerline to position of min distance to point. negative is behind prop, positive is in front of prop
        centerline_point = pos+self._prop_forward*centerline_dist[:, np.newaxis]#position on centerline closest to the control point
        center2point_vec = control_points-centerline_point #shortest vector from control point to centerline
        r_cp = self._vec_mag_mult(center2point_vec) #distance from center line to control point
        tangent_vec = np.cross(self._prop_forward,center2point_vec/r_cp[:,None])#direction of tangential velocity
        stream_loc = np.where((abs(r_cp)<=(self._d/2))&(centerline_dist<0.))#indices of control points that fall within uncontracted propwash cylinder

        #determine velocities at control points within streamtube
        s = -centerline_dist[stream_loc]
        Vxi,Vti = self._Vxi,self._Vti

        if s.size == 0:
            return np.zeros_like(control_points)


        R = self._d/2
        r = self._r

        kd = 1+(s/np.sqrt((s*s)+(R*R)))

        r_prime = np.empty([r.size,s.size])
        r_prime[0] = r[0] #nacelle radius, assume it is constant with hub radius for now

        Vx2 = Vxi[1:,None]+Vxi[0:-1,None]
        Kv = (2*self._Vinf+Vx2)/(2*self._Vinf+kd[None,:]*Vx2)
        for i in range(1,r.size):
            r_prime[i] = np.sqrt((r_prime[i-1]*r_prime[i-1])+((r[i]*r[i])-(r[i-1]*r[i-1]))*Kv[i-1])

        Vxim = Vxi[:,None]*kd
        Vtim = np.empty_like(Vxim)
        Vtim[int(r.size/10):][:] = 2*Vti[int(r.size/10):,None]*r[int(r.size/10):,None]/r_prime[int(r.size/10):][:]
        Vtim[0:int(r.size/10)][:] = (Vtim[int(r.size/10)][:]/r_prime[int(r.size/10)][:])*r_prime[0:int(r.size/10)][:]

        Vx_point = np.empty_like(s)
        Vt_point = np.empty_like(s)

        r_cp_in_tube = r_cp[stream_loc]

        for i in range(0,s.size):
            Vx_point[i] = np.interp(r_cp_in_tube[i],r_prime[:,i],Vxim[:,i], left=0,right=0)
            Vt_point[i] = np.interp(r_cp_in_tube[i],r_prime[:,i],Vtim[:,i], left=0,right=0)*self._rot_dir

        tangential_vel = np.zeros_like(control_points)
        axial_vel = np.zeros_like(control_points)
        tangential_vel[stream_loc] = tangent_vec[stream_loc]*Vt_point[:,None]
        axial_vel[stream_loc] = self._slip_dir*Vx_point[:,None]
        total_vel = tangential_vel+axial_vel

        return total_vel

    def _find_propwash_velocities_Epema(self,control_points):#Epema's method
        #determine which control points fall in cylinder behind prop and their respective distances along the streamtube and from the center of the streamtube
        pos = self._position
        centerline_dist = np.dot((control_points-pos),self._prop_forward)#distance down centerline to position of min distance to point. negative is behind prop, positive is in front of prop
        centerline_point = pos+self._prop_forward*centerline_dist[:, np.newaxis]#position on centerline closest to the control point
        center2point_vec = control_points-centerline_point #shortest vector from control point to centerline
        r_cp = self._vec_mag_mult(center2point_vec) #distance from center line to control point
        tangent_vec = np.cross(self._prop_forward,center2point_vec/r_cp[:,None])#direction of tangential velocity
        stream_loc = np.where((abs(r_cp)<=(self._d/2))&(centerline_dist<0.))#indices of control points that fall within uncontracted propwash cylinder

        #------based on approach and notation set forth by Epema 2017-----------
        R = self._d/2
        x = -centerline_dist[stream_loc]
        r = r_cp[stream_loc]
        
        #subterms to calculate a
        a_1 = (R*R-r*r-x*x)**2
        a_2 = np.sqrt(a_1+4*R*R*x*x)
        a_3 = (a_2+R*R-r*r-x*x)/(2*R*R)
        a = np.sqrt(a_3)

        #axial velocity scaling factor
        fva_1 = np.arcsin(R/np.sqrt(x*x+R*R))
        fva = 2+(-a+(x/R)*fva_1)

        #Slipstream contraction ratio
        J = self._J
        if J == 0:
            kd = 1+(x/np.sqrt((x*x)+(R*R)))
            Contract_ratio = np.sqrt(1/kd)
        else:
            Tc = 8*self._CT/np.pi/J/J
            b = 0.5*(-1+np.sqrt(1+Tc*(8/np.pi)))
            kd = 1+(x/np.sqrt((x*x)+(R*R)))
            Contract_ratio = np.sqrt((1+b)/(1+b*kd))

        Vx = self._Vxi_fun(r/Contract_ratio)*fva
        Vt = self._Vti_fun(r/Contract_ratio)*2

        tangential_vel = np.zeros_like(control_points)
        axial_vel = np.zeros_like(control_points)
        tangential_vel[stream_loc] = tangent_vec[stream_loc]*Vt[:,None]
        axial_vel[stream_loc] = self._slip_dir*Vx[:,None]
        total_vel = tangential_vel+axial_vel

        return total_vel

    #-------------------Goates method based on Khan approach------------------------------------------

    def _find_propwash_velocities_Goates_Khan(self,control_points):#Goates' method based on Khan approach
        if self._current_fit == False:
            self._VxiFF_fun,self._VtiFF_fun = self._find_VxFF()#fourier fit of induced velocity
            self._current_fit = True

        #determine which control points fall in cylinder behind prop and their respective distances along the streamtube and from the center of the streamtube
        pos = self._position
        centerline_dist = np.dot((control_points-pos),self._slip_dir)#distance down centerline to position of min distance to point. negative is upstream, positive is downstream
        centerline_point = pos+self._slip_dir*centerline_dist[:, np.newaxis]#position on centerline closest to the control point
        center2point_vec = control_points-centerline_point #shortest vector from control point to centerline
        r_cp = self._vec_mag_mult(center2point_vec) #distance from center line to control point
        tangent_vec = np.cross(self._prop_forward,center2point_vec/r_cp[:,None])#direction of tangential velocity
        stream_loc = np.where((abs(r_cp)<=(self._d/2+centerline_dist))&(centerline_dist>0.))#indices of control points that fall within uncontracted propwash cylinder


        x = centerline_dist[stream_loc]
        r = r_cp[stream_loc]

        xo = self._d/2#this can change. I just think its a good value to start off with
        R = self._d/2

        #find outer radius at efflux plane
        if self._Vs == 0:
            kd = 1+(xo/np.sqrt((xo*xo)+(R*R)))
            Con_ratio_o = np.sqrt(1/kd)
        else:
            Tc = 8*self._CT/np.pi/self._J/self._J
            b = 0.5*(-1+np.sqrt(1+Tc*(8/np.pi)))
            kd = 1+(xo/np.sqrt((xo*xo)+(R*R)))
            Con_ratio_o = np.sqrt((1+b)/(1+b*kd))

        Ro = R*Con_ratio_o

        #append points along efflux plane to analysis arrays to determine velocity profile @ xo
        No = 200
        ro = np.linspace(0,Ro,No)
        r = np.append(r,ro)
        x = np.append(x,np.full_like(ro,xo))

        blend_zfa = np.where(x<xo,(x/xo),1)

        if self._Vs == 0:
            kd = 1+(x/np.sqrt((x*x)+(R*R)))
            Con_ratio = np.sqrt(1/kd)
        else:
            Tc = 8*self._CT/np.pi/self._J/self._J
            b = 0.5*(-1+np.sqrt(1+Tc*(8/np.pi)))
            kd = 1+(x/np.sqrt((x*x)+(R*R)))
            Con_ratio = np.sqrt((1+b)/(1+b*kd))

        #subterms to calculate a
        a_1 = (R*R-r*r-x*x)**2
        a_2 = np.sqrt(a_1+4*R*R*x*x)
        a_3 = (a_2+R*R-r*r-x*x)/(2*R*R)
        a = np.sqrt(a_3)

        #axial velocity scaling factor
        fva_1 = np.arcsin(R/np.sqrt(x*x+R*R))
        fva = 2+(-a+(x/R)*fva_1)

        Vx_ZFA_raw = self._Vxi_fun(r/Con_ratio)*fva
        Vx_ZFA_FF = self._VxiFF_fun(r/Con_ratio)*fva

        Vt_ZFA_raw = self._Vti_fun(r/Con_ratio)*2
        Vt_ZFA_FF = self._VtiFF_fun(r/Con_ratio)*2

        #initialize all velocity values to inviscid value
        Vx = (1-blend_zfa)*Vx_ZFA_raw + blend_zfa*Vx_ZFA_FF+self._Vs #add freestream component in stream direction
        Vt = (1-blend_zfa)*Vt_ZFA_raw + blend_zfa*Vt_ZFA_FF

        #equivalent jet profile
        Uo = self._equivalent_jet_GK(Vx[-No:],r[-No:])

        #determine length of ZFE
        U_ratio = self._Vs/Uo
        l_zfe = 2*Ro*np.sqrt(1+U_ratio)/np.sqrt(2)/self._bg/(1-U_ratio)
        zfe_loc = np.where((x<xo+l_zfe) & (x>xo))
        zef_loc = np.where(x>xo+l_zfe)

        if self._Vs != 0:
            self._integrate_coflow_GK(Uo,2*r[-1],xo,l_zfe)

        #correct velocities in zone of flow establishment
        Vx[zfe_loc] = self._find_zfe_GK(x[zfe_loc],r[zfe_loc],Vx[-No:],Vt[-No],r[-No:],Uo,xo,l_zfe)
        Vx[zef_loc] = self._find_zef_GK(x[zef_loc],r[zef_loc],xo,r[-1],Uo)

        Vx = Vx[:-No]-self._Vs#remove efflux plane points and change to excess(induced) velocity
        Vt = Vt[:-No]

        tangential_vel = np.zeros_like(control_points)
        axial_vel = np.zeros_like(control_points)
        tangential_vel[stream_loc] = tangent_vec[stream_loc]*Vt[:,None]
        axial_vel[stream_loc] = self._slip_dir*Vx[:,None]
        total_vel = tangential_vel+axial_vel

        return total_vel

    def _integrate_coflow_GK(self,Uo,Do,xo,l_zfe):
        Meo = Do*Do*np.pi*Uo*(Uo-self._Vs)/4#excess momentum at efflux plane
        self._l_m = np.sqrt(Meo)/self._Vs#momentum length scale
        self._B = Do/np.sqrt(1+self._Vs/Uo)#top hat half width at end of ZFE

        #initial conditions for ODE at beginning of ZEF
        Bs = [self._B/self._l_m]
        Us = -0.5+np.sqrt(1+4/(np.pi*Bs[-1]*Bs[-1]))/2
        xs = [(xo+l_zfe)/self._l_m]

        #setup ODE solver
        f = ode(self._coflow_spread_GK)
        f.set_integrator('dopri5')
        f.set_initial_value(Bs[-1],xs[-1])

        #xs step size and max value of iterations
        dxs = self._d/5/self._l_m
        iters = 0
        max_iters = 200

        #step through xs range
        while f.successful() and iters<max_iters:
            f.integrate(f.t+dxs)
            xs.append(f.t)
            Bs.append(f.y)
            iters+=1

        Bs = np.array(Bs)
        xs = np.array(xs)

        x = xs*self._l_m

        #create interpolation function
        self._Bs_fun = interp1d(x,Bs.flatten(),kind = 'cubic',fill_value = 'extrapolate')


    def _coflow_spread_GK(self, xs, Bs):
        Us = -0.5+np.sqrt(1+4/(np.pi*Bs*Bs))/2
        dBs = np.sqrt(2)*self._bg*Us/(1+Us)
        return dBs

    def _find_zfe_GK(self,x,r,Vxo,Vto,ro,Uo,xo,l_zfe):
        if self._Vs == 0:
            b = self._bg*(x-xo)
        else:
            b_end = self._B/np.sqrt(2)
            b = b_end*(x-xo)/l_zfe

        Ro = ro[-1]
        r_integ = np.linspace(0,Ro*10,ro.size*10)

        #determine excess momentum at efflux plane
        Meo = np.pi*Ro*Ro*Uo*(Uo-self._Vs)

        #setup tophat and raw profiles for blending
        tophat = np.where(r_integ<=Ro, Uo, self._Vs)
        profile = np.full_like(r_integ,self._Vs)
        profile[:ro.size] = Vxo

        #blend tophat and fourier velocity profiles together
        blend = (x-xo)/l_zfe
        temp_U = (1-blend[:,None])*profile[None,:]+blend[:,None]*tophat[None,:]

        #determine radius of mixing region start and velocity at that point
        R_mix = -Ro*(x-xo)/l_zfe+Ro
        #U_Rmix = np.zeros_like(R_mix)
        #for i in range(0,R_mix.size):
        #    U_Rmix[i] = np.interp(R_mix[i],r_integ,temp_U[i])

        U_Rmix_fun = interp1d(r_integ,temp_U,kind = 'linear',axis = 1)
        U_Rmix = np.diagonal(U_Rmix_fun(R_mix))

        U_mix = (U_Rmix[:,None]-self._Vs)*np.exp(-((r_integ[None,:]-R_mix[:,None])**2)/(b[:,None]*b[:,None]))+self._Vs
        temp_U = np.where(r_integ[None,:]<R_mix[:,None],temp_U,U_mix)


        U = self._conserve_momentum_GK(temp_U,r_integ,Meo,U_Rmix,R_mix,b)

        #interpolate velocity at desired r
        Vx = np.zeros_like(r)
        for i in range(0,r.size):
            Vx[i] = np.interp(r[i],r_integ,U[i])

        return Vx

    def _conserve_momentum_GK(self, temp_U, r_integ, Meo, U_Rmix,R_mix, b,error = 1E-10):
        #use secant method to determine necessary Vx scaling factor to conserve momentum in modified profile
        r_full = np.broadcast_to(np.expand_dims(r_integ,0),temp_U.shape)
        core = np.where(r_full<R_mix[:,None])

        scale0 = np.ones_like(R_mix)
        scale1 = np.full_like(scale0,1.1)
        Me0 = self._calc_momentum_zfe_GK(temp_U, r_full, r_integ,R_mix,b,scale0)-Meo
        Me1 = self._calc_momentum_zfe_GK(temp_U, r_full, r_integ,R_mix,b,scale1)-Meo

        scale2 = np.copy(scale0)
        i = 0
        while True:
            loc = np.where(abs((scale1-scale0)/scale0)>error)
            scale2[loc] = scale1[loc]-((Me1[loc]*(scale1[loc]-scale0[loc]))/(Me1[loc]-Me0[loc]))
            i+=1
            if loc[0].size == 0:
                break
            scale0 = np.copy(scale1)
            scale1 = np.copy(scale2)
            Me0 = np.copy(Me1)
            Me1 = self._calc_momentum_zfe_GK(temp_U, r_full, r_integ,R_mix,b,scale1)-Meo

        U = scale2[:,None]*(temp_U-self._Vs)+self._Vs

        return U 

    def _calc_momentum_zfe_GK(self, U, r_full, r_integ, R_mix, b,scale = None):
        if scale is None:
            scale = np.ones_like(R_mix)
        scaled_U = ((U-self._Vs)*scale[:,None])+self._Vs

        U_Rmix_fun = interp1d(r_integ,scaled_U,kind = 'linear',axis = 1)
        U_Rmix = np.diagonal(U_Rmix_fun(R_mix))

        #determine excess momentum of scaled_U profile
        Ume = U_Rmix-self._Vs

        Me_mix = np.pi*Ume*Ume*b*(np.sqrt(np.pi)*R_mix*((1/np.sqrt(2))+self._Vs/Ume)+b*(0.5+self._Vs/Ume))#mixing region
        

        core_U = np.where(r_full<R_mix[:,None],scaled_U,self._Vs)
        Me_core = 2*np.pi*simps(core_U*(core_U-self._Vs)*r_full,r_full)

        Me_u = Me_mix+Me_core

        return Me_u

    def _find_zef_GK(self,x,r,xo,Ro,Uo):
        if self._Vs == 0:
            b = self._bg*(x-xo)
            Um = Uo*(1/np.sqrt(2)/self._bg)*2*Ro/(x-xo)
        else:
            Bs = self._Bs_fun(x)
            b = Bs*self._l_m/np.sqrt(2)
            Us = -0.5+np.sqrt(1+4/(np.pi*Bs*Bs))/2
            dU = Us*self._Vs
            Um = 2*dU

        Vx = Um*np.exp(-((r/b)**2))+self._Vs
        return Vx


    def _equivalent_jet_GK(self,Vx,ro):
        Ro = ro[-1]
        integ = (8/(Ro*Ro))*simps(Vx*(Vx-self._Vs)*ro,ro)
        root = np.sqrt((self._Vs*self._Vs)+integ)
        Uo = (self._Vs+root)/2
        return Uo

    #---------------------------Goates method based on Stone's inviscid approach with viscous------------------
    #---------------------------corrections based on turbulent jet correlations--------------------------------
    @profile
    def _find_propwash_velocities_Goates(self,control_points):
        #determine which control points fall in cylinder behind prop and their respective distances along the streamtube and from the center of the streamtube
        pos = self._position
        centerline_dist = np.dot((control_points-pos),self._slip_dir)#distance down centerline to position of min distance to point. negative is upstream, positive is downstream
        centerline_point = pos+self._slip_dir*centerline_dist[:, np.newaxis]#position on centerline closest to the control point
        center2point_vec = control_points-centerline_point #shortest vector from control point to centerline
        r_cp = self._vec_mag_mult(center2point_vec) #distance from center line to control point
        tangent_vec = np.cross(self._prop_forward,center2point_vec/r_cp[:,None])#direction of tangential velocity
        stream_loc = np.where((abs(r_cp)<=(self._d/2+centerline_dist))&(centerline_dist>0.))#indices of control points that fall within uncontracted propwash cylinder


        x = centerline_dist[stream_loc]
        r = r_cp[stream_loc]

        R = self._d/2
        Vxi = self._Vxi
        Vti = self._Vti
        r_prop = self._r

        #excess momentum and equivalent jet in plane of prop
        Me_prop = 2*np.pi*simps(Vxi*(Vxi+self._Vs)*r_prop, r_prop)
        Uo_prop = 0.5*(self._Vs+np.sqrt(self._Vs*self._Vs+4*Me_prop/np.pi/R/R))

        #very rough guess for ZFE length based on initial stream
        x_end = self._d*np.sqrt(1+(self._Vs/Uo_prop))/(np.sqrt(2)*self._bgx*(1-(self._Vs/Uo_prop)))
        max_x = np.amax(x)
        if max_x > x_end:
            x_end = max_x
        #control points are created out to 1.5*xe_estimate to provide data points off which to find the real xe
        N = 100
        x = np.append(x,np.linspace(0,1.5*x_end,N))

        kd = 1+(x/np.sqrt((x*x)+(R*R)))#slipstream development factor 

        r_prime = np.empty([x.size,r_prop.size])
        r_prime[:,0] = 0.001*self._d#r_prop[0]#nacelle radius, need to address this as it will strongly affect tangential velocity

        Vx2 = Vxi[1:]+Vxi[0:-1]

        Kv = (2*self._Vs+Vx2[None,:])/(2*self._Vs+kd[:,None]*Vx2[None,:])
        r_prop_2 = r_prop*r_prop
        for i in range(1,r_prop.size):
            r_prime[:,i] = np.sqrt((r_prime[:,i-1]*r_prime[:,i-1])+(r_prop_2[i]-r_prop_2[i-1])*Kv[:,i-1])

        Vxim = Vxi[None,:]*kd[:,None]
        Vtim = Vti*2*(r_prop/r_prime)

        #calculate excess momentum of inviscid slipstream at each x position of control points
        Mes = np.empty_like(x)
        for i in range(0,x.size):
            Mes[i] = 2*np.pi*simps(Vxim[i]*(Vxim[i]+self._Vs)*r_prime[i], r_prime[i])

        #calculate swirling axial excess momentum
        Ms = np.empty_like(x)
        for i in range(0,x.size):
            Ms[i] = simps((Vxim[i]*(Vxim[i]+self._Vs)-0.5*(Vtim[i]*Vtim[i]))*r_prime[i], r_prime[i])

        #calculate swirling angular momentum
        Ls = np.empty_like(x)
        for i in range(0,x.size):
            Ls[i] = simps(Vxim[i]*Vtim[i]*r_prime[i]*r_prime[i], r_prime[i])#unsure whether Vxim or (Vxim+Vs) should be used here....

        Rs = r_prime[:,-1]#outer radius of slipstream at each x position of control points


        #find equivalent axial and tangential profiles that conserve axial and tangential momentum
        du, dw = self._equivalent_velocities(Ms,Ls,Rs,x)


        S = Ls/Ms/Rs

        #spread rate based on swirl number
        beta_g = np.tan(np.radians(4.8+14*S))/np.sqrt(-np.log(0.5))
        bgx = self._bgx
        bgt = beta_g-bgx

        self._Ms_fun = interp1d(x[-N:],Ms[-N:],kind = 'cubic',fill_value = 'extrapolate')
        self._Ls_fun = interp1d(x[-N:],Ls[-N:],kind = 'cubic',fill_value = 'extrapolate')
        self._du_fun = interp1d(x[-N:],du[-N:],kind = 'cubic',fill_value = 'extrapolate')
        self._dw_fun = interp1d(x[-N:],dw[-N:],kind = 'cubic',fill_value = 'extrapolate')
        self._bgt_fun = interp1d(x[-N:],bgt[-N:],kind = 'cubic',fill_value = 'extrapolate')

        xe,b_xe,um_xe,wm_xe = self._find_swirl_xe(du[-N:],dw[-N:],Ms[-N:],Ls[-N:],Rs[-N:],bgx,bgt[-N:],x[-N:],N)

        M_xe = self._Ms_fun(xe)
        L_xe = self._Ls_fun(xe)


        #integrate ZEF
        self._integrate_ZEF(b_xe,M_xe,L_xe,um_xe,wm_xe,xe)

        #remove additional points used to find xe
        x = np.delete(x,np.s_[-N:])
        r_prime = np.delete(r_prime,np.s_[-N:],axis = 0)
        Vxim = np.delete(Vxim,np.s_[-N:],axis = 0)
        Vtim = np.delete(Vtim,np.s_[-N:],axis = 0)
        Rs = np.delete(Rs,np.s_[-N:])
        Ms = np.delete(Ms,np.s_[-N:])
        Ls = np.delete(Ls,np.s_[-N:])
        du = np.delete(du,np.s_[-N:])
        dw = np.delete(dw,np.s_[-N:])
        bgt = np.delete(bgt,np.s_[-N:])

        Mes = np.delete(Mes,np.s_[-N:])

        Uo = 0.5*(self._Vs+np.sqrt(self._Vs*self._Vs+4*Mes/np.pi/Rs/Rs))#uniform total jet velocity of equivalent excess axial momentum at each x position of control points
        '''
        #predict location of end of ZFE and tophat half radius at that location
        xe,Be = self._find_xe(Mes[-N:],Uo[-N:],beta_g[-N:],x[-N:],N)
        Mee = np.interp(xe,x[-N:],Mes[-N:])

        beta_g_fun = interp1d(x[-N:], beta_g[-N:],kind = 'cubic',bounds_error = False,fill_value = (beta_g[-N],beta_g[-1]))
        b_fun = self._integrate_static_zfe(xe,beta_g_fun)#integrate ODE to trace progression of b based on changing swirl value


        #test to see if two different methods for half-widths line up at end of ZFE
        x_test = np.linspace(0,xe,100)
        plt.plot(x_test, b_fun(x_test))

        x_end = np.array([0,xe])
        b_end = np.array([0,Be/np.sqrt(2)])
        plt.plot(x_end,b_end)
        plt.show()
        quit()
        '''

        #add viscous effects to ZFE
        zfe = np.where(x<xe)
        zef = np.where(x>xe)
        b = np.empty_like(x)
        #assume linear expansion of mixing region in ZFE
        b[zfe] = b_xe*(x[zfe]/xe)
        b[zef] = self._bg_ZEF_fun(x[zef])
        c = b*self._tang_profile_width_ratio 
        r_wm = self._tang_profile_max_ratio*c
        '''
        if self._Vs == 0:
            b[zef] = b_xe+self._bg*(x[zef]-xe)
        else:
            Bs = self._Bs_fun(x[zef])
            b[zef] = Bs*self._l_m/np.sqrt(2)
        '''

        blend = x[zfe]/xe
        Rpc = Rs[zfe]*(1-blend)#radius of potential core

        #develop axial profiles in zone of flow establishment
        temp_U = ((1-blend[:,None])*(Vxim[zfe])+(blend*du[zfe])[:,None])+self._Vs
        temp_W = ((1-blend[:,None])*(Vtim[zfe])+(blend*dw[zfe])[:,None])


        scale_U,scale_W = self._conserve_swirl_momentum(temp_U,temp_W, r_prime[zfe],Ms[zfe],Ls[zfe], Rs[zfe],b[zfe],c[zfe],blend)

        scaled_U = (temp_U-self._Vs)*scale_U[:,None] + self._Vs
        scaled_W = temp_W*scale_W[:,None]

        Vx = np.empty_like(x)
        Vt = np.empty_like(x)


        Rpc = (1-blend)*Rs

        for i in range(scale_U.size):
            
            scaled_U_fun = interp1d(r_prime[zfe][i],scaled_U[i], kind = 'cubic', bounds_error = False, fill_value = 0)
            scaled_W_fun = interp1d(r_prime[zfe][i],scaled_W[i], kind = 'cubic', bounds_error = False, fill_value = 0)

            U_Rpc = scaled_U_fun(Rpc[i])
            Ume = U_Rpc-self._Vs



            #develop tangential velocity profile
            c_xe = c[zfe][i]/blend[i]
            r_wm_xe = c_xe*self._tang_profile_max_ratio

            r_1 = blend[i]*r_wm_xe
            r_2 = (1-blend[i])*Rs[i]+blend[i]*r_wm_xe
            r_3 = (1-blend[i])*Rs[i]+blend[i]*c_xe

            W_r1 = scaled_W_fun(r_1)
            W_r2 = scaled_W_fun(r_2)
            r_w = np.linspace(0,r_3,500)

            W_visc = np.empty_like(r_w)
            inner_mix = np.where(r_w<r_1)
            outer_mix = np.where(r_w>r_2)
            no_mix = np.where((r_w>r_1)&(r_w<r_2))

            W_visc[inner_mix] = (r_w[inner_mix]/r_1)*W_r1
            W_visc[no_mix] = scaled_W_fun(r_w[no_mix])
            W_visc[outer_mix] = (-W_r2/(r_3-r_2))*(r_w[outer_mix]-r_3)

            Vt[i] = np.interp(r[i],r_w,W_visc,left = 0, right = 0)

            if r[i]<Rpc[i]:
                Vx[i] = scaled_U_fun(r[i])
            else:
                Vx[i] = (Ume*np.exp(-((r[i]-Rpc[i])/b[zfe][i])**2))+self._Vs
                

        '''
        
        U = self._conserve_momentum(temp_U,r_prime[zfe],Mes[zfe],Rpc,b[zfe])

        U_Rpc = np.empty_like(Rpc)
        for i in range(Rpc.size):
            U_Rpc[i] = np.interp(Rpc[i],r_prime[zfe][i],U[i])

        Ume_zfe = U_Rpc-self._Vs

        Vx_zfe = np.zeros_like(r[zfe])
        #inside potential core
        for i in range(0,r[zfe].size):
            center = (1-blend[i])*self._Vs+blend[i]*Uo[i]
            Vx_zfe[i] = np.interp(r[zfe][i],r_prime[zfe][i],U[i], left=center,right=0)
        #in mixing region
        Vx_zfe = np.where(r[zfe]>Rpc, Ume_zfe*np.exp(-((r[zfe]-Rpc)**2)/(b[zfe]*b[zfe]))+self._Vs,Vx_zfe)

        #centerline velocity in ZEF is based on inviscid excess momentum at that point
        Ume_zef = -self._Vs+np.sqrt(self._Vs*self._Vs+(2*Mes[zef])/(np.pi*b[zef]*b[zef]))
        Vx_zef = Ume_zef*np.exp(-((r[zef])**2)/(b[zef]*b[zef]))+self._Vs

        Vx = np.empty_like(x)
        Vx[zfe] = Vx_zfe
        Vx[zef] = Vx_zef
        Vx = Vx-self._Vs

        Vt = np.empty_like(x)

        for i in range(0,x.size):
            Vt[i] = np.interp(r[i],r_prime[i,:],Vtim[i,:], left=0,right=0)*self._rot_dir
        '''

        Vx = Vx-self._Vs

        tangential_vel = np.zeros_like(control_points)
        axial_vel = np.zeros_like(control_points)
        tangential_vel[stream_loc] = tangent_vec[stream_loc]*Vt[:,None]
        axial_vel[stream_loc] = self._slip_dir*Vx[:,None]
        total_vel = tangential_vel+axial_vel

        return total_vel

    def _integrate_ZEF(self,bg,Ms,Ls,um,wm,xe):

        #determine tophat profiles at xe
        initial_guess = np.array([bg,um/2,wm/2])
        sol = opt.root(self._tophat_at_xe,initial_guess,args = (bg,um,Ms,Ls))
        if sol.success:
            B_xe = sol.x[0]
            U_xe = sol.x[1]
            W_xe = sol.x[2]
        else:
            raise RuntimeError("Unable to determine tophat profiles at transition from ZFE to ZEF")

        #integrate spreading hypothesis starting at xe
        #evaluate momentum equations to determine changes in U and W with changing width downstream
        #setup ODE solver

        B = [B_xe]
        x = [xe]

        f = ode(self._expansion_rate_ZEF)
        f.set_integrator('dopri5')
        f.set_initial_value(B[-1],x[-1])

        #xs step size and max value of iterations
        dx = xe/50
        iters = 0
        max_iters = 200

        #step through xs range
        while f.successful() and iters<max_iters:
            f.integrate(f.t+dx)
            x.append(f.t)
            B.append(f.y)
            iters+=1

        B = np.array(B)
        x = np.array(x)
        
        U = []
        W = []
        bg_zef = []
        um_zef = []
        wm_zef = []
        initial_guess_top = np.array([10,10])
        initial_guess_self = np.array([B[0],10,10])
        for i in range(B.size):
            M = self._Ms_fun(x[i])
            L = self._Ls_fun(x[i])
            sol = opt.root(self._tophat_velocities,initial_guess_top,args = ([B[i]],M,L))
            if sol.success:
                U.append(sol.x[0])
                W.append(sol.x[1])
            else:
                raise RuntimeError("Unable to determine tophat profiles at transition from ZFE to ZEF")
            initial_guess_top = np.array([U[-1],W[-1]])

            sol = opt.root(self._self_similar_velocities,initial_guess_self,args = (B[i],M,L,U[i]))
            if sol.success:
                bg_zef.append(sol.x[0])
                um_zef.append(sol.x[1])
                wm_zef.append(sol.x[2])
            else:
                raise RuntimeError("Unable to determine tophat profiles at transition from ZFE to ZEF")
            initial_guess_self = np.array([bg_zef[-1],um_zef[-1],wm_zef[-1]])


        #create interpolation function
        self._B_ZEF_fun = interp1d(x,B.flatten(),kind = 'cubic',fill_value = 'extrapolate')
        self._bg_ZEF_fun = interp1d(x,bg_zef,kind = 'cubic',fill_value = 'extrapolate')
        self._um_ZEF_fun = interp1d(x,um_zef,kind = 'cubic',fill_value = 'extrapolate')
        self._wm_ZEF_fun = interp1d(x,wm_zef,kind = 'cubic',fill_value = 'extrapolate')

    def _expansion_rate_ZEF(self, x, B):
        M = self._Ms_fun(x)
        L = self._Ls_fun(x)

        #determine tophat profiles at xe
        initial_guess = np.array([10,10])
        sol = opt.root(self._tophat_velocities,initial_guess,args = (B,M,L))
        if sol.success:
            U = sol.x[0]
            W = sol.x[1]
        else:
            raise RuntimeError("Unable to determine tophat profiles at transition from ZFE to ZEF")

        bgx = self._bgx
        bgt = self._bgt_fun(x)
        dB = (bgx*np.absolute(U)+bgt*np.absolute(W))/np.sqrt((self._Vs+U)*(self._Vs+U)+W*W)
        return dB

    def _self_similar_velocities(self,x0,B,M,L,U):
        bg = x0[0]
        um = x0[1]
        wm = x0[2]
        mass_zero = bg*bg*um-B*B*U

        #adjust these values to match experimental data
        c = bg*self._tang_profile_width_ratio 
        r_wm = self._tang_profile_max_ratio*c

        #chunks of axial momentum equation
        m0 = 0.25*(bg*bg*um)*(um+2*self._Vs)
        m1 = 0.5*((wm*r_wm)/2)**2
        m2 = 0.5*(wm/(r_wm-c))**2
        m3 = -(3*(r_wm**4)-8*c*(r_wm**3)+6*c*c*r_wm*r_wm-c**4)/12

        M_zero = (m0-m1-(m2*m3))-M

        r_L = np.linspace(0,c,100)
        u_L = um*np.exp(-((r_L/bg)**2))
        w_L = np.where(r_L<r_wm,wm*(r_L/r_wm),(wm/(r_wm-c))*(r_L-c))

        L_zero = simps(u_L*w_L*r_L*r_L,r_L)-L

        return (mass_zero,M_zero,L_zero)

    def _tophat_velocities(self,x0,B,M,L):
        U = x0[0]
        W = x0[1]
        B = B[-1]
        M_zero = (B*B/2)*(U*(U+self._Vs)-(W*W/2))-M
        L_zero = (B*B*B/3)*U*W-L
        return (M_zero,L_zero)

    def _tophat_at_xe(self,x0,bg,um,M,L):
        B = x0[0]
        U = x0[1]
        W = x0[2]
        mass_zero = bg*bg*um-B*B*U
        M_zero = (B*B/2)*(U*(U+self._Vs)-(W*W/2))-M
        L_zero = (B*B*B/3)*U*W-L

        return (mass_zero,M_zero,L_zero)

    def _find_swirl_xe(self,du,dw,Ms,Ls,Rs,bgx,bgt,x,N):
        xe0 = 6.2*self._d
        xe1 = xe0*1.2
        LHS0,RHS0,vel0 = self._swirl_xe_imbalance(xe0,du,dw,Ms,Ls,Rs,bgx,bgt,x,N)
        LHS1,RHS1,vel1 = self._swirl_xe_imbalance(xe1,du,dw,Ms,Ls,Rs,bgx,bgt,x,N)
        imbal0 = LHS0-RHS0
        imbal1 = LHS1-RHS1
        i = 0
        while True:
            xe2 = xe1-((imbal1*(xe1-xe0))/(imbal1-imbal0))
            i+=1
            if abs(xe2-xe1)<1E-12:
                return xe2,LHS1,vel1[0],vel1[1]
            xe0=xe1
            imbal0=imbal1
            xe1=xe2
            LHS1,RHS1,vel1 = self._swirl_xe_imbalance(xe1,du,dw,Ms,Ls,Rs,bgx,bgt,x,N)
            imbal1 = LHS1-RHS1

    def _swirl_xe_imbalance(self,xe,du,dw,Ms,Ls,Rs,bgx,bgt,x,N):


        x_ZFE = np.linspace(0,xe,N)
        du_ZFE = self._du_fun(x_ZFE)
        dw_ZFE = self._dw_fun(x_ZFE)
        bgt_ZFE = self._bgt_fun(x_ZFE)

        #determine mixing layer width at proposed xe based on spreading hypothesis
        spread_bg = simps((bgx*np.absolute(du/2)+bgt*np.absolute(dw/2))/np.sqrt((self._Vs+du/2)*(self._Vs+du/2)+(dw/2)*(dw/2)),x_ZFE)
        M_xe = self._Ms_fun(xe)
        L_xe = self._Ls_fun(xe)

        #determine mixing layer width and tangential velocity magnitude at proposed xe using momentum of self-similar profiles
        similar_bg,um,wm = self._similar_momentum(M_xe,L_xe,du_ZFE[-1],dw_ZFE[-1],spread_bg)
        velocities = (um,wm)
        return spread_bg,similar_bg,velocities

    def _similar_momentum(self,M,L,du,dw,spread_bg):
        um = du
        #find bg and wm from momentum equations
        initial_guess = np.array([spread_bg,dw])
        sol = opt.root(self._root_of_similar_momentum,initial_guess,args = (M,L,um))
        if sol.success:
            bg = sol.x[0]
            wm = sol.x[1]
        else:
            raise RuntimeError("Unable to locate transition from ZEF to ZFE")

        return bg,um,wm

    def _root_of_similar_momentum(self,x0,M,L,du):
        bg = x0[0]
        wm = x0[1]
        um = du

        #adjust these values to match experimental data
        c = bg*self._tang_profile_width_ratio 
        r_wm = self._tang_profile_max_ratio*c

        #chunks of axial momentum equation
        m0 = 0.25*(bg*bg*um)*(um+2*self._Vs)
        m1 = 0.5*((wm*r_wm)/2)**2
        m2 = 0.5*(wm/(r_wm-c))**2
        m3 = -(3*(r_wm**4)-8*c*(r_wm**3)+6*c*c*r_wm*r_wm-c**4)/12

        M_zero = (m0-m1-(m2*m3))-M

        r_L = np.linspace(0,c,100)
        u_L = um*np.exp(-((r_L/bg)**2))
        w_L = np.where(r_L<r_wm,wm*(r_L/r_wm),(wm/(r_wm-c))*(r_L-c))

        L_zero = simps(u_L*w_L*r_L*r_L,r_L)-L

        return M_zero,L_zero


    def _equivalent_velocities(self,Ms,Ls,Rs,x):
        #find ui and wi (magnitude of equivalent axial and tangential velocities, constant radially)
        N = Ms.size
        du = []
        dw = []
        initial_guess = np.full(2,100)
        for i in range(N):
            sol = opt.root(self._root_of_equivalent_velocities,initial_guess,args=(Ms[i],Ls[i],Rs[i]))
            if sol.success:
                #print(i,': It worked! ', sol.nfev)
                du.append(sol.x[0])
                dw.append(sol.x[1])
                initial_guess = sol.x
            else:
                raise RuntimeError("Unable to calculate equivalent jet velocities")

        return np.array(du), np.array(dw)


    def _root_of_equivalent_velocities(self,x0,Ms,Ls,Rs):
        du = x0[0]
        dw = x0[1]

        root_M = ((du*(du+self._Vs)-(dw*dw/2))*Rs*Rs/2)-Ms
        root_L = (du*dw*Rs*Rs*Rs/3)-Ls

        return [root_M,root_L]


    def _find_xe(self, Me,Uo,beta_g,x,N):
        xe0 = 6.2*self._d
        xe1 = xe0*1.2
        LHS0,RHS0 = self._xe_imbalance(xe0,Me,Uo,beta_g,x,N)
        LHS1,RHS1 = self._xe_imbalance(xe1,Me,Uo,beta_g,x,N)
        imbal0 = LHS0-RHS0
        imbal1 = LHS1-RHS1

        while True:
            xe2 = xe1-((imbal1*(xe1-xe0))/(imbal1-imbal0))
            if abs(xe2-xe1)<1E-12:
                return xe2,LHS1
            xe0=xe1
            imbal0=imbal1
            xe1=xe2
            LHS1,RHS1 = self._xe_imbalance(xe1,Me,Uo,beta_g,x,N)
            imbal1 = LHS1-RHS1

    def _xe_imbalance(self,xe,Me,Uo,beta_g,x,N):
        Me_fun = interp1d(x,Me,kind = 'cubic',fill_value = 'extrapolate')
        Uo_fun = interp1d(x,Uo,kind = 'cubic',fill_value = 'extrapolate')

        Me_xe = Me_fun(xe)
        Uo_xe = Uo_fun(xe)

        LHS = 2*np.sqrt(Me_xe/(np.pi*(Uo_xe*Uo_xe-self._Vs*self._Vs)))

        x_ZFE = np.linspace(0,xe,N)
        Uo_ZFE = Uo_fun(x_ZFE)

        RHS = simps(np.sqrt(2)*beta_g*(Uo_ZFE-self._Vs)/(Uo_ZFE+self._Vs),x_ZFE)

        return LHS,RHS

    def _integrate_static_zfe(self,xe,beta_g_fun):


        b = [0]
        x = [0]

        iters = 0
        max_iters = 100

        dx = xe/max_iters

        f = ode(self._db_static_zfe)
        f.set_integrator('dopri5')
        f.set_initial_value(b[-1],x[-1])
        f.set_f_params(beta_g_fun)

        while f.successful() and iters<max_iters:
            f.integrate(f.t+dx)
            x.append(f.t)
            b.append(f.y)
            iters +=1

        b = np.array(b)
        x = np.array(x)


        b_fun = interp1d(x,b.flatten(),kind = 'cubic',fill_value = 'extrapolate')

        return b_fun

    def _db_static_zfe(self,x,b,beta_g_fun):
        db = beta_g_fun(x)
        return db


    def _integrate_coflow(self,xe,Be,Mee):#Uo,Do,xo,l_zfe):
        #Meo = Do*Do*np.pi*Uo*(Uo-self._Vs)/4#excess momentum at efflux plane
        self._l_m = np.sqrt(Mee)/self._Vs#momentum length scale
        
        #initial conditions for ODE at beginning of ZEF
        Bs = [Be/self._l_m]#initialize list
        Us = -0.5+np.sqrt(1+4/(np.pi*Bs[-1]*Bs[-1]))/2
        xs = [xe/self._l_m]


        #setup ODE solver
        f = ode(self._coflow_spread)
        f.set_integrator('dopri5')
        f.set_initial_value(Bs[-1],xs[-1])

        #xs step size and max value of iterations
        dxs = self._d/5/self._l_m
        iters = 0
        max_iters = 200

        #step through xs range
        while f.successful() and iters<max_iters:
            f.integrate(f.t+dxs)
            xs.append(f.t)
            Bs.append(f.y)
            iters+=1

        Bs = np.array(Bs)
        xs = np.array(xs)

        x = xs*self._l_m

        #create interpolation function
        self._Bs_fun = interp1d(x,Bs.flatten(),kind = 'cubic',fill_value = 'extrapolate')


    def _coflow_spread(self, xs, Bs):
        Us = -0.5+np.sqrt(1+4/(np.pi*Bs*Bs))/2
        dBs = np.sqrt(2)*self._bg*Us/(1+Us)
        return dBs

    def _conserve_swirl_momentum(self,temp_U,temp_W, r_prime,Ms,Ls, Rs,b,c,blend):
        scale_U = []
        scale_W = []

        initial_guess = np.ones(2)
        for i in range(Ms.size):
            sol = opt.root(self._calc_swirl_momentum_zfe,initial_guess,args = (temp_U[i],temp_W[i],r_prime[i],Ms[i],Ls[i],Rs[i],b[i],c[i],blend[i]))
            if sol.success:
                scale_U.append(sol.x[0])
                scale_W.append(sol.x[1])
            else:
                raise RuntimeError("Unable to determine correct scale to conserve momentum in ZFE")
            initial_guess[0] = sol.x[0]
            initial_guess[1] = sol.x[1] 

        scale_U = np.array(scale_U)
        scale_W = np.array(scale_W)
    
        return scale_U,scale_W

    def _calc_swirl_momentum_zfe(self,x0,temp_U,temp_W,r_prime,Ms,Ls,Rs,b,c,blend):
        scale_U = x0[0]
        scale_W = x0[1]

        scaled_U = (temp_U-self._Vs)*scale_U + self._Vs
        scaled_U_fun = interp1d(r_prime,scaled_U, kind = 'cubic', bounds_error = False, fill_value = 0)
        scaled_W = temp_W*scale_W
        scaled_W_fun = interp1d(r_prime,scaled_W, kind = 'cubic', bounds_error = False, fill_value = 0)

        Rpc = (1-blend)*Rs


        U_Rpc = scaled_U_fun(Rpc)
        Ume = U_Rpc-self._Vs



        #develop tangential velocity profile
        c_xe = c/blend
        r_wm_xe = c_xe*self._tang_profile_max_ratio

        r_1 = blend*r_wm_xe
        r_2 = (1-blend)*Rs+blend*r_wm_xe
        r_3 = (1-blend)*Rs+blend*c_xe

        W_r1 = scaled_W_fun(r_1)
        W_r2 = scaled_W_fun(r_2)
        r_w = np.linspace(0,r_3,500)

        W_visc = np.empty_like(r_w)
        inner_mix = np.where(r_w<r_1)
        outer_mix = np.where(r_w>r_2)
        no_mix = np.where((r_w>r_1)&(r_w<r_2))

        W_visc[inner_mix] = (r_w[inner_mix]/r_1)*W_r1
        W_visc[no_mix] = scaled_W_fun(r_w[no_mix])
        W_visc[outer_mix] = (-W_r2/(r_3-r_2))*(r_w[outer_mix]-r_3)
        #need to do something to get rid of the inviscid spike in the tang vel profile near the core.


        U_visc = np.where(r_w<Rpc,scaled_U_fun(r_w),(Ume*np.exp(-((r_w-Rpc)/b)**2))+self._Vs)

        #Calculate Axial Momentum
        #axial component
        core_M = np.where(r_prime<Rpc,(scaled_U*(scaled_U-self._Vs))*r_prime,0)
        Ax1 = simps(core_M,r_prime)
        Ax2 = 0.5*Ume*Ume*b*(np.sqrt(np.pi)*Rpc*((1/np.sqrt(2))+self._Vs/Ume)+b*(0.5+self._Vs/Ume))#mixing region
        Ax = Ax1+Ax2
        #tangential component
        Tang = -0.5*simps(W_visc*W_visc*r_w,r_w)
        
        M_zero = Ax+Tang-Ms

        #Calculate Angular Momentum

        L_zero = simps((U_visc-self._Vs)*W_visc*r_w*r_w,r_w)-Ls

        return M_zero,L_zero

    def _conserve_momentum(self, temp_U, r_prime, Mes,Rpc,b,error = 1E-10):
        scale0 = np.ones_like(Rpc)
        scale1 = np.full_like(scale0,1.1)
        Me0 = self._calc_momentum_zfe(temp_U,r_prime,Rpc,b,scale0)-Mes
        Me1 = self._calc_momentum_zfe(temp_U,r_prime,Rpc,b,scale1)-Mes

        scale2 = np.copy(scale0)

        i = 0
        while True:
            loc = np.where(abs((scale1-scale0)/scale0)>error)
            scale2[loc] = scale1[loc]-((Me1[loc]*(scale1[loc]-scale0[loc]))/(Me1[loc]-Me0[loc]))
            i+=1
            if loc[0].size == 0:
                break
            scale0 = np.copy(scale1)
            scale1 = np.copy(scale2)
            Me0 = np.copy(Me1)
            Me1 = self._calc_momentum_zfe(temp_U,r_prime,Rpc,b,scale1)-Mes

        U = scale2[:,None]*temp_U

        return U 

    def _calc_momentum_zfe(self,U,r,Rpc,b,scale = None):
        if scale is None:
            scale = np.ones_like(Rpc)
        scaled_U = (U-self._Vs)*scale[:,None] + self._Vs

        U_Rpc = np.empty_like(Rpc)
        for i in range(Rpc.size):
            U_Rpc[i] = np.interp(Rpc[i],r[i],scaled_U[i])

        Ume = U_Rpc-self._Vs
        Me_mix = np.pi*Ume*Ume*b*(np.sqrt(np.pi)*Rpc*((1/np.sqrt(2))+self._Vs/Ume)+b*(0.5+self._Vs/Ume))#mixing region
        
        core_U = np.where(r<Rpc[:,None],scaled_U,self._Vs)
        Me_core = 2*np.pi*simps(core_U*(core_U-self._Vs)*r,r)

        return Me_core+Me_mix


    #---------------------------------------Functions for calculating lift and drag coefficients-----------------------------------------

    def get_coefficients_alpha(self, alpha):
        CL = self._get_CL(alpha)
        CD = self._get_CD(CL,alpha)
        CL_a = self._get_CL_a(alpha)
        return CL,CL_a,CD

    def _get_CL(self,alpha):

        CL = np.empty_like(alpha)
        neg = np.where(alpha<0)
        pos = np.where(alpha>0)

        #Corrigan Stall Delay
        a_less_dA_p = alpha[pos]-self._dA[pos]
        a_less_dA_n = -alpha[neg]-self._dA[neg]

        cap = np.cos(a_less_dA_p)
        sap = np.sin(a_less_dA_p)
        can = np.cos(a_less_dA_n)
        san = np.sin(a_less_dA_n)

        #positive
        viterna_p = self._A1*np.sin(2*a_less_dA_p)+self._A2[pos]*cap*cap/sap
        linear_p = self._CL_alpha[pos]*a_less_dA_p
        step_p = (np.tanh(np.degrees(a_less_dA_p-self._a_stall[pos]))/2+0.5)
        CL[pos] = np.where(a_less_dA_p<np.radians(2),linear_p,(1-step_p)*linear_p+step_p*viterna_p)
        CL[pos] += self._CL_alpha[pos]*self._dA[pos]
        
        #negative
        viterna_n = self._A1*np.sin(2*a_less_dA_n)+self._A2_neg[neg]*can*can/san
        linear_n = self._CL_alpha[neg]*a_less_dA_n
        step_n = (np.tanh(np.degrees(a_less_dA_n-self._a_stall_neg[neg]))/2+0.5)
        CL[neg] = -np.where(a_less_dA_n<np.radians(2),linear_n,(1-step_n)*linear_n+step_n*viterna_n)
        CL[neg]-= self._CL_alpha[neg]*self._dA[neg]

        return CL

    def _get_CD(self,CL,alpha):
        CD = self._CD_Viterna(CL,alpha)
        return CD

    def _CD_Viterna(self,CL,alpha):
        CD = np.empty_like(alpha)
        ca = np.cos(alpha)
        sa = np.sin(alpha)
        pre_stall = np.where((alpha<self._delay_a_stall) & (alpha>self._delay_a_stall_neg))
        stall_pos = np.where(alpha>self._delay_a_stall)
        stall_neg = np.where(alpha<self._delay_a_stall_neg)
        CD[pre_stall] = self._CD_0[pre_stall]+self._CD_L[pre_stall]*CL[pre_stall]+self._CD_L2[pre_stall]*CL[pre_stall]*CL[pre_stall]
        CD[stall_pos] = self._B1*sa[stall_pos]*sa[stall_pos]+self._B2[stall_pos]*ca[stall_pos]
        CD[stall_neg] = self._B1*np.sin(-alpha[stall_neg])**2+self._B2_neg[stall_neg]*np.cos(-alpha[stall_neg])

        return CD

    def _get_CL_a(self,alpha):
        da = 0.001
        CL_forward = self._get_CL(alpha+da)
        CL_backward =self._get_CL(alpha-da)
        CL_a = (CL_forward-CL_backward)/2/da
        return CL_a

    #-------------------------------get characteristics functions---------------------------------

    def get_name(self):
        """Get the name of the propeller. 

        Returns
        -------
        string
            name of the propeller

        """
        return self._name

    def get_num_nodes(self):
        """Get the number of nodes in the propeller. 

        Returns
        -------
        int
            number of nodes used in blade element analysis

        """
        return self._nodes

    def get_num_blades(self):
        """Get the number of blades in the propeller. 

        Returns
        -------
        int
            number of blades in the propeller

        """
        return self._k
    
    def get_position(self):
        """Get the position of the propeller. 

        Returns
        -------
        Array
            Array containing the position [x,y,z] of the propeller

        """
        return self._position

    def get_orientation(self):
        """Get the orientation of the propeller. 

        Returns
        -------
        float
            elevation angle of propeller
        float
            heading angle of propeller

        """
        return self._theta, self._gamma

    def get_rotation_direction(self):
        """Get the rotation direction of the propeller. 

        Returns
        -------
        int
            Rotation direction of the propeller. 1 indicates CCW rotation, 
            0 indicates CW rotation.

        """
        return self._rot_dir

    def get_radial_position(self):
        """Get the radial distance to the control points of the propeller. 

        Returns
        -------
        array
            Array containing the radial distance to each of the control points

        """
        return self._r
    
    def get_chord(self):
        """Get chord of the propeller. 

        Returns
        -------
        array
            Array containing the chord of the propeller at each of the control points

        """
        return self._cb

    def get_aero_pitch_angle(self):
        """Get pitch angle of the propeller. 

        Returns
        -------
        array
            Array containing the pitch angle of the propeller at each of the control points

        """
        return self._beta

    def get_advance_angle(self):
        """Get downwash angle due to forward movement of the propeller. 

        Returns
        -------
        array
            Array containing the advance angle of the propeller at each of the control points

        """
        return self._einf

    def get_induced_angle(self):
        """Get induced downwash angle due to the other blades of the propeller. 

        Returns
        -------
        array
            Array containing the induced angle of the propeller at each of the control points

        """
        return self._ei

    def get_alpha(self):
        """Get aerodynamic angle of attack of the propeller. 

        Returns
        -------
        array
            Array containing the aerodynamic angle of attack of the propeller at each of the control points

        """
        return self._alpha

    def get_section_CL(self):
        """Get CL for each section of the propeller. 

        Returns
        -------
        array
            Array containing the section lift coefficient at each of the control points

        """
        return self._CL

    def get_section_CD(self):
        """Get CD for each section of the propeller. 

        Returns
        -------
        array
            Array containing the section drag coefficient at each of the control points

        """
        return self._CD

    def get_zero_lift_alpha(self):
        """Get zero lift angle of attack of propeller. 

        Returns
        -------
        array
            Array containing the zero lift angle of attack at each of the control points

        """
        return self._alpha_L0

    def get_Vi(self):
        """Get total induced velocity of the propeller. 

        Returns
        -------
        array
            Array containing the total induced velocity at each of the control points

        """
        return self._Vi

    def get_axial_Vi(self):
        """Get axial induced velocity of the propeller. 

        Returns
        -------
        array
            Array containing the axial induced velocity at each of the control points

        """
        return self._Vxi

    def get_tangential_Vi(self):
        """Get tangential induced velocity of the propeller. 

        Returns
        -------
        array
            Array containing the tangential induced velocity at each of the control points

        """
        return self._Vti


    #---------------------------------------helpful assist functions-----------------------------------------

    def _import_data(self, filename):
        data = np.loadtxt(filename)
        x = data[:,0]
        y = data[:,1]
        return x,y

    def _linearInterp(self, left, right, array):
        slope = (right-left)/(array[-1]-array[0])
        inter = left+((array-array[0])*slope)
        return inter

    def _vec_mag_mult(self,vec):
        return np.sqrt(vec[:,0]**2+vec[:,1]**2+vec[:,2]**2)

    def _vec_angle(self, v1,v2):
        a,b,c = v1
        d,e,f = v2
        dot = a*d+b*e+c*f
        mag = m.sqrt(a*a+b*b+c*c)*m.sqrt(d*d+e*e+f*f)
        return m.acos(dot/mag)
