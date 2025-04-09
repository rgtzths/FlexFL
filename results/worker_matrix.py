import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import plotly.io as pio   

pio.kaleido.scope.mathjax = None

# 0 -> didnt work
# 1 -> worked
# 2 -> didnt work and failed
# 3 -> worked and failed
# 4 -> worked and failed after finishing working

#          | epoch 1 | epoch 2 | ...
# worker 1 |
# worker 2 |

data = [
        [2, 1, 1, 2, 0, 1, 0, 3, 0, 1],
        [1, 0, 1, 1, 1, 0, 3, 1, 1, 0],
        [1, 1, 0, 1, 1, 0, 4, 0, 3, 2],
        [1, 1, 0, 3, 1, 1, 1, 2, 0, 3],
        [4, 0, 3, 3, 1, 1, 1, 0, 1, 3],
        [3, 1, 1, 0, 3, 0, 1, 1, 1, 1],
        [0, 1, 1, 3, 0, 3, 1, 1, 1, 1],
        [1, 1, 0, 4, 0, 1, 2, 1, 1, 1],
        [3, 1, 3, 1, 1, 1, 1, 1, 2, 0],
        [2, 0, 1, 2, 3, 1, 0, 1, 1, 1],
]

df = pd.DataFrame(data)
df.index = [f"{i+1}" for i in range(df.shape[0])]
df.columns = [f"{i+1}" for i in range(df.shape[1])]

color_map = {
    0: "#0000FF",  # blue
    1: "#228B22",  # green
    2: "#FFA500",  # orange
    3: "#FF0000",  # red
    4: "#FFD700",  # yellow
}

# Match color to value in flattened data
custom_colorscale = [[i / 4, color_map[i]] for i in range(5)]

# Plot image without colorbar
fig = px.imshow(
    df,
    labels=dict(x="Epoch", y="Worker", color="Status Code"),
    x=df.columns,
    y=df.index,
    color_continuous_scale=custom_colorscale
)
fig.update_layout(
    coloraxis_showscale=False
)

# Add manual legend markers
legend_items = {
    "0: Idle": color_map[0],
    "1: Worked": color_map[1],
    "2: Failed while idle": color_map[2],
    "3: Failed while working": color_map[3],
    "4: Failed after working": color_map[4],
}

for i, (label, color) in enumerate(legend_items.items()):
    fig.add_trace(go.Scatter(
        x=[None],
        y=[None],
        mode='markers',
        marker=dict(size=10, color=color, symbol='square'),
        legendgroup=label,
        showlegend=True,
        name=label,
    ))
fig.update_yaxes(title_standoff=5)
fig.update_layout(
    legend=dict(
        orientation="h",
        yanchor="bottom",
        y=1.02,
        xanchor="center",
        x=0.5,
        title_text="",
    ),
    width=800,
    height=600,
    margin=dict(l=0, r=0, t=0, b=50),
)

# fig.show()
fig.write_image("results/heatmap.png")