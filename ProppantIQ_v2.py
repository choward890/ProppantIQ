#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Wed Oct 17 11:29:15 2024

Updates: fixing plot flashing while data is being plotted

@author: coltonhoward
"""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.io as pio
from fpdf import FPDF    
import tempfile          
import os
import io
import time
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4, landscape

st.set_page_config(layout="wide")

# Footer section
footer = """
<style>
footer {
    position: fixed;
    bottom: 0;
    left: 0;
    width: 100%;
    background-color: #44475a;
    color: #f8f8f2;
    text-align: center;
    padding: 10px;
    font-size: 14px;
    box-shadow: 0 -2px 5px rgba(0, 0, 0, 0.2);
}
a {
    color: #bd93f9;
    text-decoration: none;
}
</style>
<footer>
    Made with ❤️ | Liberty Energy 
</footer>
"""

st.markdown(footer, unsafe_allow_html=True)

# Streamlit < 1.50 can visually flicker when Plotly charts rerender.
# Mirror the upstream overflow fix locally so live updates are less jarring.
plotly_flicker_fix_css = """
<style>
[data-testid="stPlotlyChart"] {
    overflow: hidden !important;
}
[data-testid="stPlotlyChart"] > div {
    overflow: hidden !important;
}
[data-testid="stPlotlyChart"] .js-plotly-plot,
[data-testid="stPlotlyChart"] .plot-container,
[data-testid="stPlotlyChart"] .svg-container {
    overflow: hidden !important;
}
</style>
"""
st.markdown(plotly_flicker_fix_css, unsafe_allow_html=True)

# Place the logo and title side by side
col_logo, col_title = st.columns([1, 5])

logo_html = """
<a href="https://libertyenergy.com/" target="_blank">
    <img src="	https://libertyenergy.com/wp-content/uploads/2023/05/Liberty-Energy-Horizontal-Logo.png" 
         alt="Liberty Energy Logo" style="width: 400px;"/>
</a>
"""
st.markdown(logo_html, unsafe_allow_html=True)

st.title('ProppantIQ ⛱️')

# -------------------- Keep track of parameter change events --------------------
if "param_change_events" not in st.session_state:
    st.session_state["param_change_events"] = []

def watch_param(param_key: str, new_value) -> None:
    """
    Compare the old value in session_state with new_value.
    If changed, store an event with the current x (if available)
    and the param name + new value.
    """
    old_key = param_key + "_old"
    old_value = st.session_state.get(old_key, None)
    if old_value is not None and old_value != new_value:
        if not st.session_state["x_full"].empty:
            last_x = st.session_state["x_full"].iloc[-1]
        else:
            last_x = 0
        st.session_state["param_change_events"].append({
            "x": last_x,
            "param": param_key,
            "new_val": new_value
        })
    st.session_state[old_key] = new_value

# -------------------- Function to clear all data --------------------
def clear_all_data():
    """
    Resets session-state variables that hold data, plots, and states.
    This effectively wipes out everything, allowing the user to start fresh.
    """
    # Turn off or reset any 'modes' and counters
    st.session_state.running = False
    st.session_state.paused = False
    st.session_state.analysis_mode = False
    st.session_state.index = 0
    st.session_state.last_fig = None
    st.session_state.last_full_boxes_consumed_calc = 0
    st.session_state["box_swap_until"] = 0.0
    st.session_state["box_swap_audio_nonce"] = 0
    st.session_state["box_swap_audio_rendered_nonce"] = 0
    st.session_state["main_fig"] = None
    st.session_state["main_fig_signature"] = None
    st.session_state["analysis_fig_signature"] = None

    # Clear param-change events
    st.session_state["param_change_events"] = []

    # Clear analysis plots
    st.session_state["analysis_figs"] = []
    st.session_state["analysis_plots_created"] = False

    # Clear data arrays
    variables_to_initialize = [
        'x_full', 'y1_full', 'y3_full', 'y4_full', 'y5_full', 'y6_full',
        'calc_ppa_ppr_full', 'calc_ppa_smooth_full', 'calc_clean_rate_full',
        'delta_t_full', 'incremental_clean_volume_full', 'total_calc_clean_volume_full',
        'incremental_proppant_full', 'calc_total_proppant_full'
    ]
    for var in variables_to_initialize:
        st.session_state[var] = pd.Series(dtype=float)

# Sidebar
st.sidebar.title("Settings")

# 1. File Upload
with st.sidebar.expander("1. File Upload", expanded=True):
    uploaded_file = st.file_uploader("Choose a CSV file", type="csv")

if uploaded_file is not None:
    data = pd.read_csv(uploaded_file, skiprows=[1])  # Skip second line (units)
    st.sidebar.success(f"File uploaded: {uploaded_file.name}")
    columns = data.columns.tolist()

    base_name = os.path.splitext(uploaded_file.name)[0]
    output_filename = f"{base_name}_simulated_data.csv"

    # 2. CSV Channel Mapping
    with st.sidebar.expander("2. CSV Channel Mapping", expanded=True):
        x_column = st.selectbox("Time ⤵️", columns, key='x_column')
        y1_column = st.selectbox("Actual Prop Concentration ⤵️ (calculating input)", columns, key='y1_column')
        y3_column = st.selectbox("Total Slurry Rate ⤵️", columns, key='y3_column')
        y4_column = st.selectbox("Pressure ⤵️", columns, key='y4_column')
        y5_column = st.selectbox("Total Proppant ⤵️", columns, key='y5_column')
        y6_column = st.selectbox("Design Prop Concentration ⤵️", columns, key='y6_column')

    # -------------------- Control Buttons (incl. Clear All Data) --------------------
    col1, col2, col3, col4, col5, col6 = st.columns(6)
    with col1:
        start_button = st.button("Start/Restart")
    with col2:
        pause_button = st.button("Pause")
    with col3:
        resume_button = st.button("Resume")
    with col4:
        defaults_button = st.button("Calculation Defaults")
    with col5:
        analysis_button = st.button("Analysis")
    with col6:
        clear_data_button = st.button("Clear All Data")

    # Manage state
    if 'running' not in st.session_state:
        st.session_state.running = False
    if 'paused' not in st.session_state:
        st.session_state.paused = False
    if 'index' not in st.session_state:
        st.session_state.index = 0
    if 'last_fig' not in st.session_state:
        st.session_state.last_fig = None
    if 'analysis_mode' not in st.session_state:
        st.session_state.analysis_mode = False
    if 'last_full_boxes_consumed_calc' not in st.session_state:
        st.session_state['last_full_boxes_consumed_calc'] = 0
    if "box_swap_until" not in st.session_state:
        st.session_state["box_swap_until"] = 0.0
    if "box_swap_audio_nonce" not in st.session_state:
        st.session_state["box_swap_audio_nonce"] = 0
    if "box_swap_audio_rendered_nonce" not in st.session_state:
        st.session_state["box_swap_audio_rendered_nonce"] = 0
    if "main_fig" not in st.session_state:
        st.session_state["main_fig"] = None
    if "main_fig_signature" not in st.session_state:
        st.session_state["main_fig_signature"] = None
    if "analysis_fig_signature" not in st.session_state:
        st.session_state["analysis_fig_signature"] = None

    if "analysis_figs" not in st.session_state:
        st.session_state["analysis_figs"] = []
    if "analysis_plots_created" not in st.session_state:
        st.session_state["analysis_plots_created"] = False

    if clear_data_button:
        clear_all_data()
        st.success("All data and plots have been cleared. You can upload a new file or start fresh.")

    variables_to_initialize = [
        'x_full', 'y1_full', 'y3_full', 'y4_full', 'y5_full', 'y6_full',
        'calc_ppa_ppr_full', 'calc_ppa_smooth_full', 'calc_clean_rate_full',
        'delta_t_full', 'incremental_clean_volume_full', 'total_calc_clean_volume_full',
        'incremental_proppant_full', 'calc_total_proppant_full'
    ]
    for var in variables_to_initialize:
        if var not in st.session_state:
            st.session_state[var] = pd.Series(dtype=float)

    if defaults_button:
        st.session_state['base_density'] = 8.33
        st.session_state['specific_gravity'] = 2.65
        st.session_state['ppr'] = 45
        st.session_state['pt_prop_factor'] = 1.0
        st.session_state['high_cal'] = 15.19
        st.session_state['low_cal'] = 8.33
        st.session_state['baby_beast'] = 1.0

    # 3. Simulation Parameters
    with st.sidebar.expander("3. Simulation Parameters", expanded=False):
        delay = st.number_input("Delay (ms):", min_value=100, value=st.session_state.get('delay', 1000), step=100, key='delay')
        index_increment = st.number_input("Index rows:", min_value=1, value=st.session_state.get('index_increment', 10), step=1, key='index_increment')
        smoothing_window = st.number_input("Prop Smooth:", min_value=1, value=st.session_state.get('smoothing_window', 10), step=1, key='smoothing_window')

        show_csv_boxes = st.checkbox("Show Design Boxes", value=st.session_state.get('show_csv_boxes', False))
        st.session_state['show_csv_boxes'] = show_csv_boxes
        show_calc_boxes = st.checkbox("Show Calculated Boxes", value=st.session_state.get('show_calc_boxes', True))
        st.session_state['show_calc_boxes'] = show_calc_boxes

    # 4. Calculation Parameters
    with st.sidebar.expander("4. Calculation Parameters", expanded=False):
        base_density_new = st.number_input(
            "Base Density:",
            min_value=0.1,
            value=st.session_state.get('base_density', 8.33),
            key='base_density'
        )
        watch_param('base_density', base_density_new)

        specific_gravity_new = st.number_input(
            "Sand SG:",
            min_value=0.1,
            value=st.session_state.get('specific_gravity', 2.65),
            key='specific_gravity'
        )
        watch_param('specific_gravity', specific_gravity_new)

        ppr_new = st.number_input("PPR:", min_value=1, value=st.session_state.get('ppr', 45), key='ppr')
        watch_param('ppr', ppr_new)

        pt_prop_factor_new = st.number_input("PT Factor:", min_value=0.1, value=st.session_state.get('pt_prop_factor', 1.0), key='pt_prop_factor')
        watch_param('pt_prop_factor', pt_prop_factor_new)

        high_cal_new = st.number_input("High Cal:", min_value=0.1, value=st.session_state.get('high_cal', 15.19), key='high_cal')
        watch_param('high_cal', high_cal_new)

        low_cal_new = st.number_input("Low Cal:", min_value=0.1, value=st.session_state.get('low_cal', 8.33), key='low_cal')
        watch_param('low_cal', low_cal_new)

        baby_beast_new = st.number_input("Baby Beast Factor", min_value=0.1, value=st.session_state.get('baby_beast', 1.0), key='baby_beast')
        watch_param('baby_beast', baby_beast_new)

    # Local variable shortcuts
    base_density = st.session_state.base_density
    specific_gravity = st.session_state.specific_gravity
    ppr = st.session_state.ppr
    pt_prop_factor = st.session_state.pt_prop_factor
    high_cal = st.session_state.high_cal
    low_cal = st.session_state.low_cal
    baby_beast = st.session_state.baby_beast
    delay = st.session_state.delay
    index_increment = st.session_state.index_increment
    smoothing_window = st.session_state.smoothing_window

    x_min = data[x_column].min()
    x_max = data[x_column].max() * 1.05
    y1_max = data[y1_column].max() * 1.5
    y3_max = data[y3_column].max() * 1.2
    y4_max = data[y4_column].max() * 1.05

    # Colors
    calc_prop_color = '#FF5F1F'        # Calc Prop Conc
    y2_color = '#17becf'               # Calc Clean Rate
    y3_color = '#0349fc'               # Total Slurry Rate
    y4_color = '#ff0000'               # Pressure
    total_prop_color = '#808080'       # Design Prop Pumped
    total_calc_prop_color = '#FFA500'  # Actual Prop Pumped
    delta_prop_color = '#9FE2BF'       # Ahead/Behind difference
    cum_clean_vol_color = '#0D84E6'    # total clean volume

    plot_placeholder = st.empty()
    numerical_values_placeholder = st.empty()
    boxes_placeholder_csv = st.empty()
    boxes_placeholder_calc = st.empty()
    analysis_placeholder = st.empty()
    box_swap_placeholder = st.empty()

    # ------------------ Start/Restart/Pause/Resume/Analysis actions ------------------
    if start_button:
        st.session_state.running = True
        st.session_state.paused = False
        st.session_state.analysis_mode = False
        st.session_state.index = 0
        for var in variables_to_initialize:
            st.session_state[var] = pd.Series(dtype=float)
        st.session_state['last_full_boxes_consumed_calc'] = 0
        st.session_state["box_swap_until"] = 0.0
        st.session_state["box_swap_audio_nonce"] = 0
        st.session_state["box_swap_audio_rendered_nonce"] = 0
        st.session_state["main_fig"] = None
        st.session_state["main_fig_signature"] = None
        st.session_state["analysis_fig_signature"] = None
        st.session_state["analysis_figs"].clear()
        st.session_state["analysis_plots_created"] = False

    if pause_button:
        st.session_state.paused = True
        st.session_state.running = False

    if resume_button:
        if st.session_state.paused:
            st.session_state.running = True
            st.session_state.paused = False

    if analysis_button:
        st.session_state.analysis_mode = not st.session_state.analysis_mode

    # ------------------ Utility & calculation functions ------------------
    def perform_calculations_on_new_data(x_new, y1_new, y3_new, y4_new, y5_new):
        """Pseudo calculation logic for prop concentration & proppant totals."""
        avf = (1 / (8.33 * specific_gravity))
        ppr_calc = ppr / 45

        # Some pseudo steps for demonstration
        slurry = -0.000009 * y1_new**4 + 0.0007 * y1_new**3 - 0.0244 * y1_new**2 + 0.6125 * y1_new + 8.3362
        ppa_shift = (slurry - base_density) / (1 - slurry * avf)
        delta_ppa = y1_new - ppa_shift
        low_point = (15.191 - high_cal)
        high_point = (15.191 + low_point - low_cal) / (1 - (15.191 + low_point) * avf)
        constant = (high_point - 0) / (88)
        calibrated_ppa = constant + constant * (y1_new - 0.25) / 0.25
        ppa_after_cal_shift = calibrated_ppa - delta_ppa

        calc_ppa_ppr_new = ((ppa_after_cal_shift / ppr_calc) * baby_beast) / pt_prop_factor
        calc_ppa_smooth_new = calc_ppa_ppr_new.rolling(window=int(smoothing_window), center=True, min_periods=1).mean().round(2)

        ppa_new = calc_ppa_ppr_new
        avf = 1 / (8.33 * specific_gravity)
        cfr_new = 1 / (ppa_new * avf + 1)
        calc_clean_rate_new = y3_new * cfr_new
        delta_t_new = x_new.diff().fillna(0)
        incremental_clean_volume_new = calc_clean_rate_new * delta_t_new

        if not st.session_state.total_calc_clean_volume_full.empty:
            total_calc_clean_volume_new = (
                st.session_state.total_calc_clean_volume_full.iloc[-1]
                + incremental_clean_volume_new.cumsum()
            )
        else:
            total_calc_clean_volume_new = incremental_clean_volume_new.cumsum()

        incremental_proppant_new = incremental_clean_volume_new * 42 * ppa_new
        if not st.session_state.calc_total_proppant_full.empty:
            calc_total_proppant_new = (
                st.session_state.calc_total_proppant_full.iloc[-1]
                + incremental_proppant_new.cumsum()
            )
        else:
            calc_total_proppant_new = incremental_proppant_new.cumsum()

        # Append new results to session state
        st.session_state.x_full = pd.concat([st.session_state.x_full, x_new], ignore_index=True)
        st.session_state.y1_full = pd.concat([st.session_state.y1_full, y1_new], ignore_index=True)
        st.session_state.y3_full = pd.concat([st.session_state.y3_full, y3_new], ignore_index=True)
        st.session_state.y4_full = pd.concat([st.session_state.y4_full, y4_new], ignore_index=True)
        st.session_state.y5_full = pd.concat([st.session_state.y5_full, y5_new], ignore_index=True)
        st.session_state.calc_ppa_ppr_full = pd.concat([st.session_state.calc_ppa_ppr_full, calc_ppa_ppr_new], ignore_index=True)
        st.session_state.calc_ppa_smooth_full = pd.concat([st.session_state.calc_ppa_smooth_full, calc_ppa_smooth_new], ignore_index=True)
        st.session_state.calc_clean_rate_full = pd.concat([st.session_state.calc_clean_rate_full, calc_clean_rate_new], ignore_index=True)
        st.session_state.delta_t_full = pd.concat([st.session_state.delta_t_full, delta_t_new], ignore_index=True)
        st.session_state.incremental_clean_volume_full = pd.concat([st.session_state.incremental_clean_volume_full, incremental_clean_volume_new], ignore_index=True)
        st.session_state.total_calc_clean_volume_full = pd.concat([st.session_state.total_calc_clean_volume_full, total_calc_clean_volume_new], ignore_index=True)
        st.session_state.incremental_proppant_full = pd.concat([st.session_state.incremental_proppant_full, incremental_proppant_new], ignore_index=True)
        st.session_state.calc_total_proppant_full = pd.concat([st.session_state.calc_total_proppant_full, calc_total_proppant_new], ignore_index=True)

        return st.session_state.calc_total_proppant_full.iloc[-1]

    def display_boxes(boxes_consumed, total_boxes, num_boxes_to_display, label, container):
        with container.container():
            st.write(f"**{label} Boxes**")
            total_boxes = int(total_boxes)
            num_boxes_to_display = int(num_boxes_to_display)
            if total_boxes <= 0:
                st.write("No boxes to display.")
                return
            cols = st.columns(num_boxes_to_display)
            for i in range(num_boxes_to_display):
                box_label = f"{i + 1}"
                start_capacity = i * 25000
                end_capacity = (i + 1) * 25000
                consumed_in_box = min(max(boxes_consumed * 25000 - start_capacity, 0), 25000)
                fill_percentage = (consumed_in_box / 25000) * 100
                box_html = f'''
                    <div style="text-align:center;">
                        <div style="position: relative; width: 30px; height: 60px; border:1px solid black; background-color: #EE2827;">
                            <div style="
                                position: absolute;
                                top: 0;
                                left: 0;
                                width: 100%;
                                height: {fill_percentage}%;
                                background-color: #262626;
                            "></div>
                        </div>
                        <div style="font-size:10px;">{box_label}</div>
                    </div>
                '''
                cols[i].markdown(box_html, unsafe_allow_html=True)

    def colored_metric(label, value, color):
        return f"""
        <div style="text-align: center;">
            <p style="margin: 0; font-size: 16px; color: {color};">{label}</p>
            <p style="margin: 0; font-size: 24px; color: {color}; font-weight: bold;">{value}</p>
        </div>
        """

    def get_current_metrics():
        if st.session_state.y5_full.empty:
            return None

        current_calc_total_proppant = st.session_state.calc_total_proppant_full.iloc[-1]
        current_y5_value = st.session_state.y5_full.iloc[-1]
        current_cumulative_clean_vol = (
            st.session_state.total_calc_clean_volume_full.iloc[-1]
            if not st.session_state.total_calc_clean_volume_full.empty
            else 0.0
        )

        return {
            "calc_ppa_smooth": st.session_state.calc_ppa_smooth_full.iloc[-1],
            "calc_clean_rate": st.session_state.calc_clean_rate_full.iloc[-1],
            "y3": st.session_state.y3_full.iloc[-1],
            "y4": st.session_state.y4_full.iloc[-1],
            "y5": current_y5_value,
            "calc_total_proppant": current_calc_total_proppant,
            "y6": st.session_state.y6_full.iloc[-1],
            "cumulative_clean_vol": current_cumulative_clean_vol,
            "prop_diff": current_calc_total_proppant - current_y5_value,
        }

    def advance_simulation_step():
        if not st.session_state.running or st.session_state.index >= len(data):
            st.session_state.running = False
            return False

        start_index = st.session_state.index
        end_index = min(start_index + int(st.session_state.index_increment), len(data))

        x_new = data[x_column].iloc[start_index:end_index].reset_index(drop=True)
        y1_new = data[y1_column].iloc[start_index:end_index].reset_index(drop=True)
        y3_new = data[y3_column].iloc[start_index:end_index].reset_index(drop=True)
        y4_new = data[y4_column].iloc[start_index:end_index].reset_index(drop=True)
        y5_new = data[y5_column].iloc[start_index:end_index].reset_index(drop=True)
        y6_new = data[y6_column].iloc[start_index:end_index].reset_index(drop=True)

        perform_calculations_on_new_data(x_new, y1_new, y3_new, y4_new, y5_new)
        st.session_state.y6_full = pd.concat([st.session_state.y6_full, y6_new], ignore_index=True)
        st.session_state.index = end_index

        current_calc_total_proppant = st.session_state.calc_total_proppant_full.iloc[-1]
        full_boxes_consumed_calc = int(current_calc_total_proppant / 25000)
        if full_boxes_consumed_calc > st.session_state['last_full_boxes_consumed_calc']:
            st.session_state['last_full_boxes_consumed_calc'] = full_boxes_consumed_calc
            st.session_state["box_swap_until"] = time.time() + 2
            st.session_state["box_swap_audio_nonce"] += 1

        if st.session_state.index >= len(data):
            st.session_state.running = False

        return True

    def build_param_change_points(y_series):
        if st.session_state.x_full.empty or y_series.empty:
            return [], [], []

        event_x = []
        event_y = []
        event_text = []
        for evt in st.session_state.get("param_change_events", []):
            evt_x = evt["x"]
            idx = (st.session_state.x_full - evt_x).abs().argmin()
            event_x.append(st.session_state.x_full.iloc[idx])
            event_y.append(y_series.iloc[idx])
            event_text.append(f"{evt['param']} -> {evt['new_val']}")

        return event_x, event_y, event_text

    def create_main_figure():
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=[],
            y=[],
            name='Calc Prop Conc',
            line=dict(color=calc_prop_color),
            yaxis='y1',
            hovertemplate='%{y:.2f}'
        ))
        fig.add_trace(go.Scatter(
            x=[],
            y=[],
            name='Design Prop Conc',
            line=dict(color='green'),
            yaxis='y1',
            hovertemplate='%{y:.2f}'
        ))
        fig.add_trace(go.Scatter(
            x=[],
            y=[],
            name='Calc Clean Rate',
            line=dict(color=y2_color),
            yaxis='y3'
        ))
        fig.add_trace(go.Scatter(
            x=[],
            y=[],
            name=y3_column,
            line=dict(color=y3_color),
            yaxis='y3'
        ))
        fig.add_trace(go.Scatter(
            x=[],
            y=[],
            name=y4_column,
            line=dict(color=y4_color),
            yaxis='y4'
        ))
        fig.add_trace(go.Scatter(
            x=[],
            y=[],
            mode='markers',
            text=[],
            hovertemplate='%{text}<extra></extra>',
            marker=dict(symbol='diamond', color='red', size=10),
            name='Calc Changes'
        ))
        fig.update_layout(
            xaxis=dict(domain=[0.05, 0.95], range=[x_min, x_max]),
            yaxis=dict(
                title=dict(text="Prop Conc", font=dict(color='green')),
                range=[0, y1_max],
                showgrid=True,
                tickfont=dict(color='green')
            ),
            yaxis3=dict(
                title=dict(text="Rate (bpm)", font=dict(color=y3_color)),
                tickfont=dict(color=y3_color),
                anchor='free',
                overlaying='y',
                side='right',
                position=0.9,
                range=[0, y3_max],
                showgrid=False,
            ),
            yaxis4=dict(
                title=dict(text=y4_column, font=dict(color=y4_color)),
                tickfont=dict(color=y4_color),
                anchor='free',
                overlaying='y',
                side='right',
                position=0.95,
                range=[0, y4_max],
                showgrid=False,
            ),
            legend=dict(
                x=0.5,
                y=1.15,
                xanchor='center',
                orientation='h'
            ),
            margin=dict(l=0, r=0, t=30, b=10),
            autosize=True,
            uirevision="main-live-plot",
        )
        return fig

    def build_main_figure():
        if st.session_state.x_full.empty:
            return None

        current_signature = (y3_column, y4_column, x_min, x_max, y1_max, y3_max, y4_max)
        if (
            st.session_state.get("main_fig") is None
            or st.session_state.get("main_fig_signature") != current_signature
        ):
            st.session_state["main_fig"] = create_main_figure()
            st.session_state["main_fig_signature"] = current_signature

        fig = st.session_state["main_fig"]
        x_values = st.session_state.x_full.tolist()
        fig.data[0].x = x_values
        fig.data[0].y = st.session_state.calc_ppa_smooth_full.tolist()
        fig.data[1].x = x_values
        fig.data[1].y = st.session_state.y6_full.tolist()
        fig.data[2].x = x_values
        fig.data[2].y = st.session_state.calc_clean_rate_full.tolist()
        fig.data[3].x = x_values
        fig.data[3].y = st.session_state.y3_full.tolist()
        fig.data[3].name = y3_column
        fig.data[4].x = x_values
        fig.data[4].y = st.session_state.y4_full.tolist()
        fig.data[4].name = y4_column

        param_event_x, param_event_y, param_event_text = build_param_change_points(
            st.session_state.calc_ppa_smooth_full
        )
        fig.data[5].x = param_event_x
        fig.data[5].y = param_event_y
        fig.data[5].text = param_event_text

        fig.layout.xaxis.range = [x_min, x_max]
        fig.layout.yaxis.range = [0, y1_max]
        fig.layout.yaxis3.range = [0, y3_max]
        fig.layout.yaxis4.range = [0, y4_max]
        fig.layout.yaxis4.title.text = y4_column

        return fig

    def render_box_swap_notice():
        if time.time() >= st.session_state.get("box_swap_until", 0.0):
            box_swap_placeholder.empty()
            return

        current_nonce = st.session_state.get("box_swap_audio_nonce", 0)
        with box_swap_placeholder.container():
            st.markdown("<h2 style='text-align: center; color: red;'>Box Swap</h2>", unsafe_allow_html=True)
            if current_nonce != st.session_state.get("box_swap_audio_rendered_nonce", 0):
                st.markdown(
                    """
                    <script>
                    (function() {
                        var beep = new Audio('https://actions.google.com/sounds/v1/alarms/beep_short.ogg');
                        beep.play();
                    })();
                    </script>
                    """,
                    unsafe_allow_html=True
                )
                st.session_state["box_swap_audio_rendered_nonce"] = current_nonce

    def render_live_panels():
        fig = build_main_figure()
        if fig is not None:
            st.session_state.last_fig = fig
            plot_placeholder.plotly_chart(fig, use_container_width=True, key="main_live_plot")
        elif st.session_state.last_fig is not None:
            plot_placeholder.plotly_chart(st.session_state.last_fig, use_container_width=True, key="main_live_plot")
        else:
            with plot_placeholder.container():
                st.write("Please start the simulation to see the plot and numerical values.")

        metrics = get_current_metrics()
        if metrics is None:
            numerical_values_placeholder.empty()
            boxes_placeholder_csv.empty()
            boxes_placeholder_calc.empty()
            render_box_swap_notice()
            return

        with numerical_values_placeholder.container():
            cols = st.columns(9)
            cols[0].markdown(colored_metric("Calc Prop Conc (ppa)", f"{metrics['calc_ppa_smooth']:.2f}", "orange"), unsafe_allow_html=True)
            cols[1].markdown(colored_metric("Design Prop Conc (ppa)", f"{metrics['y6']:.2f}", "green"), unsafe_allow_html=True)
            cols[2].markdown(colored_metric("Calc Clean Rate (bpm)", f"{metrics['calc_clean_rate']:.2f}", "#17becf"), unsafe_allow_html=True)
            cols[3].markdown(colored_metric("Total Clean Vol (bbl)", f"{metrics['cumulative_clean_vol']:.0f}", cum_clean_vol_color), unsafe_allow_html=True)
            cols[4].markdown(colored_metric(f"{y3_column} (bpm)", f"{metrics['y3']:.2f}", "blue"), unsafe_allow_html=True)
            cols[5].markdown(colored_metric(f"{y4_column} (psi)", f"{metrics['y4']:.0f}", "red"), unsafe_allow_html=True)
            cols[6].markdown(colored_metric("Design Prop Pumped (lbs)", f"{metrics['y5']:.0f}", "#808080"), unsafe_allow_html=True)
            cols[7].markdown(colored_metric("Actual Prop Pumped (lbs)", f"{metrics['calc_total_proppant']:,.0f}", "orange"), unsafe_allow_html=True)
            cols[8].markdown(colored_metric("Ahead / Behind (lbs)", f"{metrics['prop_diff']:,.0f}", "#9FE2BF"), unsafe_allow_html=True)

        total_proppant_max_csv = data[y5_column].max()
        total_boxes_csv = max(1, int(np.ceil(total_proppant_max_csv / 25000)))
        boxes_consumed_csv = metrics['y5'] / 25000
        num_boxes_to_display_csv = min(total_boxes_csv, 30)

        if st.session_state['show_csv_boxes']:
            display_boxes(
                boxes_consumed_csv,
                total_boxes_csv,
                num_boxes_to_display_csv,
                label="Design (CSV)",
                container=boxes_placeholder_csv
            )
        else:
            boxes_placeholder_csv.empty()

        total_proppant_max_calc = st.session_state.calc_total_proppant_full.max()
        total_boxes_calc = max(1, int(np.ceil(total_proppant_max_calc / 25000)))
        boxes_consumed_calc = metrics['calc_total_proppant'] / 25000
        num_boxes_to_display_calc = max(num_boxes_to_display_csv, min(total_boxes_calc, 30))

        if st.session_state['show_calc_boxes']:
            display_boxes(
                boxes_consumed_calc,
                total_boxes_calc,
                num_boxes_to_display_calc,
                label="Calculated",
                container=boxes_placeholder_calc
            )
        else:
            boxes_placeholder_calc.empty()

        render_box_swap_notice()

    def create_analysis_figures():
        fig_diff = go.Figure()
        fig_diff.add_trace(go.Scatter(x=[], y=[], name='Prop Difference', line=dict(color=delta_prop_color)))
        fig_diff.add_trace(go.Scatter(
            x=[],
            y=[],
            mode='markers',
            text=[],
            hovertemplate='%{text}<extra></extra>',
            marker=dict(symbol='diamond', color='red', size=10),
            name='Calc Changes'
        ))
        fig_diff.update_layout(
            title='Difference Between Actual Prop Pumped and Design Prop Pumped',
            xaxis=dict(range=[x_min, x_max]),
            xaxis_title='Time',
            yaxis_title='Difference (lbs)',
            autosize=True,
            margin=dict(l=40, r=40, t=70, b=40),
            legend=dict(orientation='h', yanchor='bottom', y=1.15, xanchor='center', x=0.5),
            uirevision="analysis-prop-diff",
        )

        fig_total_prop = go.Figure()
        fig_total_prop.add_trace(go.Scatter(x=[], y=[], name='Design Prop Pumped', line=dict(color=total_prop_color)))
        fig_total_prop.add_trace(go.Scatter(x=[], y=[], name='Actual Prop Pumped', line=dict(color=total_calc_prop_color)))
        fig_total_prop.add_trace(go.Scatter(
            x=[],
            y=[],
            mode='markers',
            text=[],
            hovertemplate='%{text}<extra></extra>',
            marker=dict(symbol='diamond', color='red', size=10),
            name='Calc Changes'
        ))
        fig_total_prop.update_layout(
            title='Time vs Design Prop Pumped vs Actual Prop Pumped',
            xaxis=dict(range=[x_min, x_max]),
            xaxis_title='Time',
            yaxis_title='Proppant (lbs)',
            autosize=True,
            margin=dict(l=40, r=40, t=80, b=40),
            legend=dict(orientation='h', yanchor='bottom', y=1.10, xanchor='center', x=0.5),
            uirevision="analysis-total-prop",
        )

        fig_prop_conc = go.Figure()
        fig_prop_conc.add_trace(go.Scatter(x=[], y=[], name='Calculated Prop Conc', line=dict(color=calc_prop_color)))
        fig_prop_conc.add_trace(go.Scatter(x=[], y=[], name='Design Prop Conc', line=dict(color='green')))
        fig_prop_conc.add_trace(go.Scatter(
            x=[],
            y=[],
            mode='markers',
            text=[],
            hovertemplate='%{text}<extra></extra>',
            marker=dict(symbol='diamond', color='red', size=10),
            name='Calc Changes'
        ))
        fig_prop_conc.update_layout(
            title='Time vs Prop Conc (Calc & Design',
            xaxis=dict(range=[x_min, x_max]),
            xaxis_title='Time',
            yaxis_title='Concentration',
            autosize=True,
            margin=dict(l=40, r=40, t=80, b=40),
            legend=dict(orientation='h', yanchor='bottom', y=1.10, xanchor='center', x=0.5),
            uirevision="analysis-prop-conc",
        )

        return [fig_diff, fig_total_prop, fig_prop_conc]

    def build_analysis_figures():
        if st.session_state.x_full.empty or st.session_state.y5_full.empty:
            return []

        current_signature = (x_min, x_max)
        if (
            len(st.session_state.get("analysis_figs", [])) != 3
            or st.session_state.get("analysis_fig_signature") != current_signature
        ):
            st.session_state["analysis_figs"] = create_analysis_figures()
            st.session_state["analysis_fig_signature"] = current_signature

        x_values = st.session_state.x_full.tolist()
        prop_diff_series = st.session_state.calc_total_proppant_full - st.session_state.y5_full
        diff_x, diff_y, diff_text = build_param_change_points(prop_diff_series)
        total_x, total_y, total_text = build_param_change_points(st.session_state.calc_total_proppant_full)
        conc_x, conc_y, conc_text = build_param_change_points(st.session_state.calc_ppa_smooth_full)

        fig_diff, fig_total_prop, fig_prop_conc = st.session_state["analysis_figs"]

        fig_diff.data[0].x = x_values
        fig_diff.data[0].y = prop_diff_series.tolist()
        fig_diff.data[1].x = diff_x
        fig_diff.data[1].y = diff_y
        fig_diff.data[1].text = diff_text
        fig_diff.layout.xaxis.range = [x_min, x_max]

        fig_total_prop.data[0].x = x_values
        fig_total_prop.data[0].y = st.session_state.y5_full.tolist()
        fig_total_prop.data[1].x = x_values
        fig_total_prop.data[1].y = st.session_state.calc_total_proppant_full.tolist()
        fig_total_prop.data[2].x = total_x
        fig_total_prop.data[2].y = total_y
        fig_total_prop.data[2].text = total_text
        fig_total_prop.layout.xaxis.range = [x_min, x_max]

        fig_prop_conc.data[0].x = x_values
        fig_prop_conc.data[0].y = st.session_state.calc_ppa_smooth_full.tolist()
        fig_prop_conc.data[1].x = x_values
        fig_prop_conc.data[1].y = st.session_state.y6_full.tolist()
        fig_prop_conc.data[2].x = conc_x
        fig_prop_conc.data[2].y = conc_y
        fig_prop_conc.data[2].text = conc_text
        fig_prop_conc.layout.xaxis.range = [x_min, x_max]

        return st.session_state["analysis_figs"]

    def render_analysis_panels():
        if not st.session_state.analysis_mode:
            analysis_placeholder.empty()
            return

        with analysis_placeholder.container():
            st.header("Data Analysis")
            analysis_figs = build_analysis_figures()
            st.session_state["analysis_figs"] = analysis_figs
            st.session_state["analysis_plots_created"] = bool(analysis_figs)

            if not analysis_figs:
                st.write("Analysis charts will appear once the simulation has plotted data.")
                return

            analysis_chart_keys = [
                "analysis_prop_diff",
                "analysis_total_prop",
                "analysis_prop_conc",
            ]
            for idx, fig_analysis in enumerate(analysis_figs):
                chart_key = analysis_chart_keys[idx] if idx < len(analysis_chart_keys) else f"analysis_chart_{idx}"
                st.plotly_chart(fig_analysis, use_container_width=True, key=chart_key)

    @st.fragment(run_every=st.session_state.delay / 1000.0)
    def live_region():
        if st.session_state.running:
            advance_simulation_step()

        render_live_panels()

    live_region()

    @st.fragment(run_every=max(st.session_state.delay / 1000.0, 1.0))
    def analysis_region():
        render_analysis_panels()

    analysis_region()

    # ------------------ CSV Download ------------------
    export_data = pd.DataFrame({
        'Time': st.session_state.x_full,
        'Actual Prop Conc (hidden)': st.session_state.y1_full,
        'Calc Prop Conc': st.session_state.calc_ppa_smooth_full,
        'Calc Clean Rate': st.session_state.calc_clean_rate_full,
        'Cumulative Clean Volume': st.session_state.total_calc_clean_volume_full,
        'Total Slurry Rate': st.session_state.y3_full,
        'Pressure': st.session_state.y4_full,
        'Design Prop Pumped': st.session_state.y5_full,
        'Actual Prop Pumped': st.session_state.calc_total_proppant_full,
        'Design Prop Conc': st.session_state.y6_full,
        'Prop Difference': st.session_state.calc_total_proppant_full - st.session_state.y5_full,
        'delta_t': st.session_state.delta_t_full,
        'Incremental Clean Volume': st.session_state.incremental_clean_volume_full,
        'Total Clean Volume': st.session_state.total_calc_clean_volume_full,  # repeated
        'Incremental Proppant': st.session_state.incremental_proppant_full,
    })
    csv = export_data.to_csv(index=False).encode('utf-8')
    st.download_button(
        label="Download Data as CSV",
        data=csv,
        file_name=output_filename,
        mime='text/csv',
    )

    # ------------------ PDF EXPORT: Using Kaleido + ReportLab ------------------
    export_pdf_button = st.button("Export Plots to PDF")
    if export_pdf_button:
        latest_fig = st.session_state.last_fig
        analysis_plots = st.session_state.get("analysis_figs", [])

        # If no figures exist, warn the user
        if not latest_fig and not analysis_plots:
            st.warning("No figures to export!")
        else:
            # We'll store PNG data for each figure, then create a PDF in memory.
            images_temp_paths = []

            def fig_to_png_bytes(fig_obj):
                """
                Convert a Plotly figure to PNG bytes (using Kaleido).
                Also handle 'Calc Changes' markers to show text statically.
                """
                fig_dict = fig_obj.to_dict()
                fig_clone = go.Figure(fig_dict)

                # Convert the 'Calc Changes' traces to always show text
                for trace_i, trace in enumerate(fig_clone.data):
                    if trace.name == 'Calc Changes':
                        fig_clone.data[trace_i].mode = 'markers+text'
                        fig_clone.data[trace_i].textposition = 'top center'
                        fig_clone.data[trace_i].hovertemplate = None

                # Remove or minimize the figure's title margin
                fig_clone.update_layout(title=None, margin=dict(t=10))

                img_bytes = pio.to_image(fig_clone, format="png", scale=2, engine='kaleido')
                return img_bytes

            # Gather figures: last (live) figure + all analysis plots
            all_figs = []
            if latest_fig:
                all_figs.append(latest_fig)
            all_figs.extend(analysis_plots)

            # Create a small progress bar
            total_figs = len(all_figs)
            progress_bar = st.progress(0)
            figs_processed = 0

            # Convert each figure to a PNG, store it in a temp file
            for fig in all_figs:
                png_bytes = fig_to_png_bytes(fig)
                with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmp_file:
                    tmp_file.write(png_bytes)
                    images_temp_paths.append(tmp_file.name)
                figs_processed += 1
                progress_bar.progress(int(figs_processed / total_figs * 100))

            progress_bar.empty()

            # Now compile these images into a single PDF using ReportLab
            pdf_buffer = io.BytesIO()
            # We'll use a landscape A4 for all pages
            c = canvas.Canvas(pdf_buffer, pagesize=landscape(A4))

            # Some margins / dimensions
            page_width, page_height = landscape(A4)
            margin = 10
            usable_width = page_width - 2 * margin
            usable_height = page_height - 2 * margin

            for img_path in images_temp_paths:
                # Add a new page for each figure
                c.drawImage(img_path, margin, margin, width=usable_width, height=usable_height, preserveAspectRatio=True)
                c.showPage()

            c.save()

            # Cleanup temp images
            for path in images_temp_paths:
                if os.path.exists(path):
                    os.remove(path)

            pdf_bytes = pdf_buffer.getvalue()

            # Provide the download button
            st.download_button(
                label="Download PDF",
                data=pdf_bytes,
                file_name="plots_analysis.pdf",
                mime="application/pdf",
            )

else:
    st.write("Please upload a CSV file from the sidebar to begin.")
    
    
    
