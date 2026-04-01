#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Wed Oct 17 11:29:15 2024

Updates: adding in audio tone for when box swap gets displayed

@author: coltonhoward
"""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.io as pio  
from fpdf import FPDF    
import tempfile          
import asyncio
import os
import time

st.set_page_config(layout="wide")

# Place the logo and title side by side
col_logo, col_title = st.columns([1, 5])
'''
with col_logo:
    st.image('/path/to/your/logo.png', width=100)  # Replace with your logo path or URL
'''

st.title('Liberty Energy Proppant Simulation - Unfinished')

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
        y6_column = st.selectbox("Design/Screw Prop Concentration ⤵️", columns, key='y6_column')

    # Control Buttons
    col1, col2, col3, col4, col5 = st.columns(5)
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

    if "analysis_figs" not in st.session_state:
        st.session_state["analysis_figs"] = []
    if "analysis_plots_created" not in st.session_state:
        st.session_state["analysis_plots_created"] = False

    # Initialize stored variables
    variables_to_initialize = [
        'x_full', 'y1_full', 'y3_full', 'y4_full', 'y5_full', 'y6_full',
        'calc_ppa_ppr_full', 'calc_ppa_smooth_full', 'calc_clean_rate_full',
        'delta_t_full', 'incremental_clean_volume_full', 'total_calc_clean_volume_full',
        'incremental_proppant_full', 'calc_total_proppant_full'
    ]
    for var in variables_to_initialize:
        if var not in st.session_state:
            st.session_state[var] = pd.Series(dtype=float)

    # Defaults
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

    # START/RESTART
    if start_button:
        st.session_state.running = True
        st.session_state.paused = False
        st.session_state.analysis_mode = False
        st.session_state.index = 0
        for var in variables_to_initialize:
            st.session_state[var] = pd.Series(dtype=float)
        st.session_state['last_full_boxes_consumed_calc'] = 0
        st.session_state["analysis_figs"].clear()
        st.session_state["analysis_plots_created"] = False

    # PAUSE
    if pause_button:
        st.session_state.paused = True
        st.session_state.running = False
        st.session_state.analysis_mode = False

    # RESUME
    if resume_button:
        if st.session_state.paused:
            st.session_state.running = True
            st.session_state.paused = False
            st.session_state.analysis_mode = False

    # ANALYSIS
    if analysis_button:
        st.session_state.running = False
        st.session_state.paused = True
        st.session_state.analysis_mode = True
        st.session_state["analysis_figs"].clear()
        st.session_state["analysis_plots_created"] = False

    # Local param copies
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

    y1_color = '#005903'
    y2_color = '#17becf'
    y3_color = '#0349fc'
    y4_color = '#ff0000'
    calc_prop_color = '#FF5F1F'
    total_prop_color = '#808080'
    total_calc_prop_color = '#800080'
    delta_prop_color = '#9FE2BF'

    plot_placeholder = st.empty()
    numerical_values_placeholder = st.empty()
    boxes_placeholder_csv = st.empty()
    boxes_placeholder_calc = st.empty()
    analysis_placeholder = st.empty()
    box_swap_placeholder = st.empty()

    def perform_calculations_on_new_data(x_new, y1_new, y3_new, y4_new, y5_new):
        """Dummy or pseudo calculation logic for prop concentration & proppant totals."""
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
            total_calc_clean_volume_new = st.session_state.total_calc_clean_volume_full.iloc[-1] + incremental_clean_volume_new.cumsum()
        else:
            total_calc_clean_volume_new = incremental_clean_volume_new.cumsum()

        incremental_proppant_new = incremental_clean_volume_new * 42 * ppa_new
        if not st.session_state.calc_total_proppant_full.empty:
            calc_total_proppant_new = st.session_state.calc_total_proppant_full.iloc[-1] + incremental_proppant_new.cumsum()
        else:
            calc_total_proppant_new = incremental_proppant_new.cumsum()

        # Append new results to the session state
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

    async def show_box_swap_message():
        # Show the "Box Swap" text
        box_swap_placeholder.markdown("<h2 style='text-align: center; color: red;'>Box Swap</h2>", unsafe_allow_html=True)
        
        # Immediately play a beep sound via JavaScript
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

        # Wait 2 seconds, then remove the "Box Swap" text
        await asyncio.sleep(2)
        box_swap_placeholder.empty()

    async def update_plot():
        while st.session_state.running and st.session_state.index < len(data):
            start_index = st.session_state.index
            end_index = st.session_state.index + index_increment
            end_index = min(end_index, len(data))

            x_new = data[x_column].iloc[start_index:end_index].reset_index(drop=True)
            y1_new = data[y1_column].iloc[start_index:end_index].reset_index(drop=True)
            y3_new = data[y3_column].iloc[start_index:end_index].reset_index(drop=True)
            y4_new = data[y4_column].iloc[start_index:end_index].reset_index(drop=True)
            y5_new = data[y5_column].iloc[start_index:end_index].reset_index(drop=True)
            y6_new = data[y6_column].iloc[start_index:end_index].reset_index(drop=True)

            current_calc_total_proppant = perform_calculations_on_new_data(
                x_new, y1_new, y3_new, y4_new, y5_new
            )
            st.session_state.y6_full = pd.concat([st.session_state.y6_full, y6_new], ignore_index=True)
            st.session_state.index = end_index

            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=st.session_state.x_full,
                y=st.session_state.y1_full,
                name=y1_column,
                line=dict(color=y1_color),
                yaxis='y1'
            ))
            fig.add_trace(go.Scatter(
                x=st.session_state.x_full,
                y=st.session_state.calc_ppa_smooth_full,
                name='Calc Prop Conc',
                line=dict(color=calc_prop_color),
                yaxis='y1',
                hovertemplate='%{y:.2f}'
            ))
            fig.add_trace(go.Scatter(
                x=st.session_state.x_full,
                y=st.session_state.y6_full,
                name='Design/Screw Prop Conc',
                line=dict(color='purple'),
                yaxis='y1',
                hovertemplate='%{y:.2f}'
            ))
            fig.add_trace(go.Scatter(
                x=st.session_state.x_full,
                y=st.session_state.calc_clean_rate_full,
                name='Calc Clean Rate',
                line=dict(color=y2_color),
                yaxis='y3'
            ))
            fig.add_trace(go.Scatter(
                x=st.session_state.x_full,
                y=st.session_state.y3_full,
                name=y3_column,
                line=dict(color=y3_color),
                yaxis='y3'
            ))
            fig.add_trace(go.Scatter(
                x=st.session_state.x_full,
                y=st.session_state.y4_full,
                name=y4_column,
                line=dict(color=y4_color),
                yaxis='y4'
            ))

            # Add markers/text for param changes
            param_events = st.session_state.get("param_change_events", [])
            param_event_x = []
            param_event_y = []
            param_event_text = []
            for evt in param_events:
                evt_x = evt["x"]
                idx = (st.session_state.x_full - evt_x).abs().argmin()
                y_val = st.session_state.y1_full.iloc[idx]
                param_event_x.append(st.session_state.x_full.iloc[idx])
                param_event_y.append(y_val)
                param_event_text.append(f"{evt['param']} -> {evt['new_val']}")

            if param_event_x:
                fig.add_trace(go.Scatter(
                    x=param_event_x,
                    y=param_event_y,
                    mode='markers+text',
                    text=param_event_text,
                    textposition='top center',
                    marker=dict(symbol='diamond', color='red', size=10),
                    name='Calc Changes'
                ))

            fig.update_layout(
                xaxis=dict(domain=[0.05, 0.95], range=[x_min, x_max]),
                yaxis=dict(
                    title="PPA",
                    titlefont=dict(color=y1_color),
                    tickfont=dict(color=y1_color),
                    range=[0, y1_max],
                    showgrid=True,
                ),
                yaxis3=dict(
                    title="Rate (bpm)",
                    titlefont=dict(color=y3_color),
                    tickfont=dict(color=y3_color),
                    anchor='free',
                    overlaying='y',
                    side='right',
                    position=0.9,
                    range=[0, y3_max],
                    showgrid=False,
                ),
                yaxis4=dict(
                    title=y4_column,
                    titlefont=dict(color=y4_color),
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
            )

            plot_placeholder.plotly_chart(fig, use_container_width=True)
            st.session_state.last_fig = fig

            # Show metrics & boxes
            current_y1_value = st.session_state.y1_full.iloc[-1]
            current_calc_ppa_smooth_value = st.session_state.calc_ppa_smooth_full.iloc[-1]
            current_calc_clean_rate_value = st.session_state.calc_clean_rate_full.iloc[-1]
            current_y3_value = st.session_state.y3_full.iloc[-1]
            current_y4_value = st.session_state.y4_full.iloc[-1]
            current_y5_value = st.session_state.y5_full.iloc[-1]
            current_y6_value = st.session_state.y6_full.iloc[-1]

            prop_diff = current_calc_total_proppant - current_y5_value

            with numerical_values_placeholder.container():
                cols = st.columns(9)
                def colored_metric(label, value, color):
                    return f"""
                    <div style="text-align: center;">
                        <p style="margin: 0; font-size: 16px; color: {color};">{label}</p>
                        <p style="margin: 0; font-size: 24px; color: {color}; font-weight: bold;">{value}</p>
                    </div>
                    """
                cols[0].markdown(colored_metric("Design Prop Conc", f"{current_y1_value:.2f}", "green"), unsafe_allow_html=True)
                cols[1].markdown(colored_metric("Calc Prop Conc", f"{current_calc_ppa_smooth_value:.2f}", "orange"), unsafe_allow_html=True)
                cols[2].markdown(colored_metric("Design/Screw Prop Conc", f"{current_y6_value:.2f}", "purple"), unsafe_allow_html=True)
                cols[3].markdown(colored_metric("Calc Clean Rate", f"{current_calc_clean_rate_value:.2f}", "#17becf"), unsafe_allow_html=True)
                cols[4].markdown(colored_metric(y3_column, f"{current_y3_value:.2f}", "blue"), unsafe_allow_html=True)
                cols[5].markdown(colored_metric(y4_column, f"{current_y4_value:.0f}", "red"), unsafe_allow_html=True)
                cols[6].markdown(colored_metric(y5_column, f"{current_y5_value:.0f}", "#808080"), unsafe_allow_html=True)
                cols[7].markdown(colored_metric("Calc Total Prop (lbs)", f"{current_calc_total_proppant:,.0f}", "#800080"), unsafe_allow_html=True)
                cols[8].markdown(colored_metric("Ahead / Behind (lbs)", f"{prop_diff:,.0f}", "#9FE2BF"), unsafe_allow_html=True)

            # Display CSV (Design) Boxes
            total_proppant_max_csv = data[y5_column].max()
            total_boxes_csv = int(np.ceil(total_proppant_max_csv / 25000))
            total_boxes_csv = max(1, total_boxes_csv)
            boxes_consumed_csv = current_y5_value / 25000
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

            # Display Calculated Boxes
            total_proppant_max_calc = st.session_state.calc_total_proppant_full.max()
            total_boxes_calc = int(np.ceil(total_proppant_max_calc / 25000))
            total_boxes_calc = max(1, total_boxes_calc)
            boxes_consumed_calc = current_calc_total_proppant / 25000
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

            # Check if a new full box was consumed in the "Calculated" series
            full_boxes_consumed_calc = int(boxes_consumed_calc)
            if full_boxes_consumed_calc > st.session_state['last_full_boxes_consumed_calc']:
                st.session_state['last_full_boxes_consumed_calc'] = full_boxes_consumed_calc
                if st.session_state['show_calc_boxes']:
                    # Trigger the beep and "Box Swap" message
                    asyncio.create_task(show_box_swap_message())

            await asyncio.sleep(delay / 1000)

            if st.session_state.paused or st.session_state.analysis_mode:
                break

        if st.session_state.index >= len(data):
            st.session_state.running = False

    # If currently running, run the update_plot asynchronously
    if st.session_state.running:
        asyncio.run(update_plot())
    else:
        # If not running, display the last figure and metrics
        if st.session_state.last_fig is not None:
            plot_placeholder.plotly_chart(st.session_state.last_fig, use_container_width=True)
            if not st.session_state.y5_full.empty:
                current_y1_value = st.session_state.y1_full.iloc[-1]
                current_calc_ppa_smooth_value = st.session_state.calc_ppa_smooth_full.iloc[-1]
                current_calc_clean_rate_value = st.session_state.calc_clean_rate_full.iloc[-1]
                current_y3_value = st.session_state.y3_full.iloc[-1]
                current_y4_value = st.session_state.y4_full.iloc[-1]
                current_y5_value = st.session_state.y5_full.iloc[-1]
                current_calc_total_proppant = st.session_state.calc_total_proppant_full.iloc[-1]
                current_total_proppant_csv = st.session_state.y5_full.iloc[-1]
                current_y6_value = st.session_state.y6_full.iloc[-1]

                prop_diff = current_calc_total_proppant - current_total_proppant_csv
                with numerical_values_placeholder.container():
                    cols = st.columns(9)
                    def colored_metric(label, value, color):
                        return f"""
                        <div style="text-align: center;">
                            <p style="margin: 0; font-size: 16px; color: {color};">{label}</p>
                            <p style="margin: 0; font-size: 24px; color: {color}; font-weight: bold;">{value}</p>
                        </div>
                        """
                    cols[0].markdown(colored_metric("Design Prop Conc", f"{current_y1_value:.2f}", "green"), unsafe_allow_html=True)
                    cols[1].markdown(colored_metric("Calc Prop Conc", f"{current_calc_ppa_smooth_value:.2f}", "orange"), unsafe_allow_html=True)
                    cols[2].markdown(colored_metric("Design/Screw Prop Conc", f"{current_y6_value:.2f}", "purple"), unsafe_allow_html=True)
                    cols[3].markdown(colored_metric("Calc Clean Rate", f"{current_calc_clean_rate_value:.2f}", "#17becf"), unsafe_allow_html=True)
                    cols[4].markdown(colored_metric(y3_column, f"{current_y3_value:.2f}", "blue"), unsafe_allow_html=True)
                    cols[5].markdown(colored_metric(y4_column, f"{current_y4_value:.0f}", "red"), unsafe_allow_html=True)
                    cols[6].markdown(colored_metric(y5_column, f"{current_y5_value:.0f}", "#808080"), unsafe_allow_html=True)
                    cols[7].markdown(colored_metric("Calc Total Prop (lbs)", f"{current_calc_total_proppant:,.0f}", "#800080"), unsafe_allow_html=True)
                    cols[8].markdown(colored_metric("Ahead / Behind (lbs)", f"{prop_diff:,.0f}", "#9FE2BF"), unsafe_allow_html=True)

                total_proppant_max_csv = data[y5_column].max()
                total_boxes_csv = int(np.ceil(total_proppant_max_csv / 25000))
                total_boxes_csv = max(1, total_boxes_csv)
                boxes_consumed_csv = current_y5_value / 25000
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
                total_boxes_calc = int(np.ceil(total_proppant_max_calc / 25000))
                total_boxes_calc = max(1, total_boxes_calc)
                boxes_consumed_calc = current_calc_total_proppant / 25000
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
        else:
            st.write("Please start the simulation to see the plot and numerical values.")

    # -- Analysis Mode / Plots --
    if st.session_state.analysis_mode:
        with analysis_placeholder.container():
            st.header("Data Analysis")
            if not st.session_state["analysis_plots_created"]:
                # 1) Plot the difference
                prop_diff_series = st.session_state.calc_total_proppant_full - st.session_state.y5_full
                fig_diff = go.Figure()
                fig_diff.add_trace(go.Scatter(
                    x=st.session_state.x_full,
                    y=prop_diff_series,
                    name='Prop Difference',
                    line=dict(color='#9FE2BF')
                ))
                
                # param-change markers on the difference line
                param_events = st.session_state.get("param_change_events", [])
                px_diff, py_diff, pt_diff = [], [], []
                for evt in param_events:
                    evt_x = evt["x"]
                    idx = (st.session_state.x_full - evt_x).abs().argmin()
                    y_val = prop_diff_series.iloc[idx]
                    px_diff.append(st.session_state.x_full.iloc[idx])
                    py_diff.append(y_val)
                    pt_diff.append(f"{evt['param']} -> {evt['new_val']}")

                if px_diff:
                    fig_diff.add_trace(go.Scatter(
                        x=px_diff,
                        y=py_diff,
                        mode='markers+text',
                        text=pt_diff,
                        textposition='top center',
                        marker=dict(symbol='diamond', color='red', size=10),
                        name='Calc Changes'
                    ))

                fig_diff.update_layout(
                    title='Difference Between Calculated Total Prop and Total Prop',
                    xaxis=dict(range=[x_min, x_max]),
                    xaxis_title='Time',
                    yaxis_title='Difference (lbs)',
                    autosize=True,
                    margin=dict(l=40, r=40, t=70, b=40),
                    legend=dict(
                        orientation='h',
                        yanchor='bottom',
                        y=1.15,        # Move the legend above the plot
                        xanchor='center',
                        x=0.5
                    )
                )
                st.session_state["analysis_figs"].append(fig_diff)

                # 2) Total Prop
                fig_total_prop = go.Figure()
                fig_total_prop.add_trace(go.Scatter(
                    x=st.session_state.x_full,
                    y=st.session_state.y5_full,
                    name='Total Prop',
                    line=dict(color='#808080')
                ))
                fig_total_prop.add_trace(go.Scatter(
                    x=st.session_state.x_full,
                    y=st.session_state.calc_total_proppant_full,
                    name='Calculated Total Prop',
                    line=dict(color='#800080')
                ))

                # param-change markers on calc total prop line
                px_tot = []
                py_tot = []
                pt_tot = []
                for evt in param_events:
                    evt_x = evt["x"]
                    idx = (st.session_state.x_full - evt_x).abs().argmin()
                    y_val = st.session_state.calc_total_proppant_full.iloc[idx]
                    px_tot.append(st.session_state.x_full.iloc[idx])
                    py_tot.append(y_val)
                    pt_tot.append(f"{evt['param']} -> {evt['new_val']}")

                if px_tot:
                    fig_total_prop.add_trace(go.Scatter(
                        x=px_tot,
                        y=py_tot,
                        mode='markers+text',
                        text=pt_tot,
                        textposition='top center',
                        marker=dict(symbol='diamond', color='red', size=10),
                        name='Calc Changes'
                    ))

                fig_total_prop.update_layout(
                    title='Time vs Total Prop and Calculated Total Prop',
                    xaxis=dict(range=[x_min, x_max]),
                    xaxis_title='Time',
                    yaxis_title='Proppant (lbs)',
                    autosize=True,
                    margin=dict(l=40, r=40, t=80, b=40),
                    legend=dict(
                        orientation='h',
                        yanchor='bottom',
                        y=1.10,
                        xanchor='center',
                        x=0.5
                    )
                )
                st.session_state["analysis_figs"].append(fig_total_prop)

                # 3) Prop Conc
                fig_prop_conc = go.Figure()
                fig_prop_conc.add_trace(go.Scatter(
                    x=st.session_state.x_full,
                    y=st.session_state.y1_full,
                    name='Design Prop Conc',
                    line=dict(color='#005903')
                ))
                fig_prop_conc.add_trace(go.Scatter(
                    x=st.session_state.x_full,
                    y=st.session_state.calc_ppa_smooth_full,
                    name='Calculated Prop Conc',
                    line=dict(color='#FF5F1F')
                ))
                fig_prop_conc.add_trace(go.Scatter(
                    x=st.session_state.x_full,
                    y=st.session_state.y6_full,
                    name='Design/Screw Prop Conc',
                    line=dict(color='purple')
                ))

                # param-change markers on calc prop line
                px_conc = []
                py_conc = []
                pt_conc = []
                for evt in param_events:
                    evt_x = evt["x"]
                    idx = (st.session_state.x_full - evt_x).abs().argmin()
                    y_val = st.session_state.calc_ppa_smooth_full.iloc[idx]
                    px_conc.append(st.session_state.x_full.iloc[idx])
                    py_conc.append(y_val)
                    pt_conc.append(f"{evt['param']} -> {evt['new_val']}")

                if px_conc:
                    fig_prop_conc.add_trace(go.Scatter(
                        x=px_conc,
                        y=py_conc,
                        mode='markers+text',
                        text=pt_conc,
                        textposition='top center',
                        marker=dict(symbol='diamond', color='red', size=10),
                        name='Calc Changes'
                    ))

                fig_prop_conc.update_layout(
                    title='Time vs Prop Conc and Calculated Prop Conc',
                    xaxis=dict(range=[x_min, x_max]),
                    xaxis_title='Time',
                    yaxis_title='Concentration',
                    autosize=True,
                    margin=dict(l=40, r=40, t=80, b=40),
                    legend=dict(
                        orientation='h',
                        yanchor='bottom',
                        y=1.10,
                        xanchor='center',
                        x=0.5
                    )
                )
                st.session_state["analysis_figs"].append(fig_prop_conc)

                st.session_state["analysis_plots_created"] = True

            for fig_analysis in st.session_state["analysis_figs"]:
                st.plotly_chart(fig_analysis, use_container_width=True)
    else:
        analysis_placeholder.empty()

    # Create DataFrame for export
    export_data = pd.DataFrame({
        'Time': st.session_state.x_full,
        'Design Prop Conc': st.session_state.y1_full,
        'Calc Prop Conc': st.session_state.calc_ppa_smooth_full,
        'Calc Clean Rate': st.session_state.calc_clean_rate_full,
        'Total Slurry Rate': st.session_state.y3_full,
        'Pressure': st.session_state.y4_full,
        'Total Prop': st.session_state.y5_full,
        'Calc Total Prop': st.session_state.calc_total_proppant_full,
        'Design/Screw Prop Conc': st.session_state.y6_full,
        'Prop Difference': st.session_state.calc_total_proppant_full - st.session_state.y5_full,
        'delta_t': st.session_state.delta_t_full,
        'Incremental Clean Volume': st.session_state.incremental_clean_volume_full,
        'Total Clean Volume': st.session_state.total_calc_clean_volume_full,
        'Incremental Proppant': st.session_state.incremental_proppant_full,
    })
    csv = export_data.to_csv(index=False).encode('utf-8')
    st.download_button(
        label="Download Data as CSV",
        data=csv,
        file_name=output_filename,
        mime='text/csv',
    )

    # -- PDF EXPORT SECTION --
    export_pdf_button = st.button("Export Plots to PDF")
    if export_pdf_button:
        latest_fig = st.session_state.last_fig
        analysis_plots = st.session_state.get("analysis_figs", [])
    
        # If no figures exist, warn the user
        if not latest_fig and not analysis_plots:
            st.warning("No figures to export!")
        else:
            # Prepare the PDF
            pdf = FPDF(orientation='L', format='A4')  # Landscape
            pdf.set_auto_page_break(auto=True, margin=15)
    
            # Function to add figures one by one
            def add_figure_to_pdf(fig_obj, pdf_object):
                fig_dict = fig_obj.to_dict()
                fig_clone = go.Figure(fig_dict)
                # Optionally remove or minimize the figure's title margin
                fig_clone.update_layout(title=None, margin=dict(t=10))
                
                # Convert figure to image bytes
                img_bytes = pio.to_image(fig_clone, format="png", scale=2)
                
                # Temporarily save as a PNG file
                with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmp:
                    tmp.write(img_bytes)
                    tmp_path = tmp.name
                
                # Add a new page and place the image
                pdf_object.add_page()
                pdf_w = pdf_object.w
                margin = 10
                pdf_object.image(tmp_path, x=margin, y=margin, w=pdf_w - 2 * margin)
    
            # Count total figures
            total_figs = 0
            if latest_fig:
                total_figs += 1
            total_figs += len(analysis_plots)
    
            # Create a progress bar and set it to 0%
            progress_bar = st.progress(0)
            figs_processed = 0
    
            # Export the last (live) figure, if it exists
            if latest_fig:
                add_figure_to_pdf(latest_fig, pdf)
                figs_processed += 1
                progress_bar.progress(int(figs_processed / total_figs * 100))
    
            # Export all analysis plots
            for fig in analysis_plots:
                add_figure_to_pdf(fig, pdf)
                figs_processed += 1
                # Update the progress bar
                progress_bar.progress(int(figs_processed / total_figs * 100))
    
            # Clear the progress bar after completion
            progress_bar.empty()
    
            # Convert PDF to bytes
            pdf_output = pdf.output(dest="S").encode("latin-1")
    
            # Provide the download button
            st.download_button(
                label="Download PDF",
                data=pdf_output,
                file_name="plots_analysis.pdf",
                mime="application/pdf",
            )

else:
    st.write("Please upload a CSV file from the sidebar to begin.")
    
    
    
