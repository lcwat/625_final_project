# EEG Recall AI API analysis pipeline
This where the storage for all of the files related to our 625 final project will reside. In this project, we apply parallelism to speed up a qualitative analysis pipeline where participant free memory recall responses are scored by an LLM. Right now, we have a minimal working example where we insert rows of participant free recall responses into a preset prompt and have an LLM score the response on recall accuracy via a standardized rubric. 

## Prerequisites
In order to get the minimal working example running on your machine, you must have a **Google AI Studio** account (free) and the unique **Gemini API key** they provide you after setting up that account. We use Gemini for our initial analysis working example because it is the only LLM API that provides a free tier for developers. 
1. Once you have your API key, you should paste the following in a **```.env```** file you create in the root of your cloned directory (this allows python to recognize your unique key as a local environmental variable):
- ```GEMINI_API_KEY=[Insert-your-API-key-here]```

3. You should also create your own virtual environment to run this python project. You can initialize a virtual environment from the command line with the following:
- ```python -m venv .venv```

4. Then, you should activate the virtual environment (varies by terminal, machine, etc.), I'll show how I do it through bash/Linux (also works for Unix/Mac terminal):
- ```source .venv/bin/activate```

5. Last, you can easily download all of the module dependencies by loading in the requirements.txt file:
- ```python -m pip install -r requirements.txt```

## Directories

- **```/scripts```** This is where the jupyter notebooks and python files will reside to run the bulk of the analysis that connects to and prompts the AI.
- **```/model_output```** This is where the final ```.csv``` output files will reside.
