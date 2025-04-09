# Backend
# create virtual environment
python -m venv venv

# install dependencies
pip install -r requirements.txt

# run project
uvicorn main:app --reload