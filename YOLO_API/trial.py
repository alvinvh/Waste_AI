from ultralytics import YOLO

# Load a pretrained YOLOv8n model
model = YOLO('best.pt')

# Define path to the image file
source = 'images/download.jpeg'

# Run inference on the source
results = model(source)  # list of Results objects