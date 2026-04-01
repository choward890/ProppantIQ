Usage Instructions for ProppantIQ

1. File Upload

   •  Upload a CSV File:
   •  Use the sidebar to upload a CSV file containing your proppant operation data.
   •  Click on the “Choose a CSV file” button and select your file.
   •  Note:
   •  The application skips the second line in the CSV file (usually containing units).
   •  Ensure your CSV file does not include units in the second row.

2. CSV Channel Mapping

   •  Map CSV Columns:
   •  In the “CSV Channel Mapping” section, map the columns from your CSV file to the required parameters:
   •  Time
   •  Design Prop Concentration
   •  Total Slurry Rate
   •  Pressure
   •  Total Proppant or anything else
   •  Use the dropdown menus to select the appropriate columns.

3. Simulation Controls

   •  Control Buttons:
   •  Start/Restart: Begin or restart the simulation.
   •  Pause: Temporarily halt the simulation.
   •  Resume: Continue the simulation after pausing.
   •  Calculate: Recalculate using new parameters without resetting the simulation.
   •  Calculation Defaults: Reset calculation parameters to their default values.
   •  Analysis: Enter analysis mode to view additional plots and insights.

4. Simulation Parameters

   •  Adjust Parameters:
   •  Delay (ms): Set the time delay between data increments in milliseconds.
   •  Index rows: Define the number of data rows to process in each increment.
   •  Prop Smooth: Specify the window size for smoothing the calculated proppant concentration.
   •  Instructors Index: Apply a scaling factor to the ‘Total Proppant’ column for calibration.

5. Calculation Parameters

   •  Modify Calculation Settings:
   •  Base Density
   •  Sand SG (Specific Gravity)
   •  PPR (Pounds per Gallon of Proppant)
   •  PT Factor
   •  High Cal
   •  Low Cal
   •  Baby Beast Factor

6. Visualization

   •  Main Plot:
   •  Displays time-series data of:
   •  Design Prop Concentration
   •  Calculated Prop Concentration
   •  Calculated Clean Rate
   •  Total Slurry Rate
   •  Pressure
   •  Interactive features allow zooming and hovering for details.
   •  Numerical Values:
   •  Current values of key metrics are displayed above the plot.
   •  Box Consumption Visualization:
   •  Simulates the consumption of proppant boxes.
   •  Separate displays for:
   •  Total Proppant (CSV)
   •  Calculated Total Proppant

7. Analysis Mode

   •  Activate Analysis:
   •  Click the “Analysis” button to enter analysis mode.
   •  Additional Plots:
   •  Proppant Difference: Visualizes discrepancies between calculated and actual total proppant.
   •  Total Proppant Over Time: Compares cumulative proppant from CSV data and calculations.
   •  Proppant Concentration Over Time: Compares design and calculated proppant concentrations.

8. Data Export

   •  Download Results:
   •  After running the simulation, download the enriched dataset by clicking the “Download Data as CSV” button.
   •  The file will be named based on your uploaded CSV file with “_simulated_data” appended.

Additional Information

Box Swap Notification

   •  Visual Alert:
   •  When a full proppant box is consumed during the simulation, a “Box Swap” message will appear.
   •  This simulates the operational need to swap out proppant boxes in real scenarios.

Session State Management

   •  The application uses Streamlit’s session state to maintain simulation progress and parameter settings between interactions.

Asynchronous Updates

   •  The simulation runs asynchronously to provide real-time updates without freezing the interface.

Troubleshooting

   •  No Plot Displayed:
   •  Ensure a CSV file is uploaded and the simulation is started.
   •  Simulation Not Responding:
   •  Check if the simulation is paused or if an error message is displayed.
   •  Incorrect Data Mapping:
   •  Verify that the correct columns are selected in the “CSV Channel Mapping” section.
