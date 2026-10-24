"""Execute a synthetic notebook through the installed Home Manager kernel."""
from pathlib import Path
import json
import nbformat
from nbclient import NotebookClient

root = Path('/home/groscoe/restore-smoke')
root.mkdir(exist_ok=True)
code = r'''
from pathlib import Path
import json, sys
import numpy as np
import pandas as pd
import scipy.stats
import matplotlib.pyplot as plt
import seaborn
import plotly.graph_objects as go
import anywidget
from bs4 import BeautifulSoup
from lxml import etree
import pyarrow.parquet as pq
import duckdb
from rapidfuzz import fuzz
from tqdm import tqdm
import openpyxl
from selenium import webdriver
import pdfplumber
import sqlite_utils
import httpx

get_ipython().run_line_magic('matplotlib', 'inline')
root = Path.cwd()
frame = pd.DataFrame({'name': ['alpha', 'beta', 'gamma'], 'value': [1, 2, 3]})
frame.to_csv(root / 'fixture.csv', index=False)
frame.to_excel(root / 'fixture.xlsx', index=False)
frame.to_parquet(root / 'fixture.parquet', index=False)
pd.testing.assert_frame_equal(frame, pd.read_csv(root / 'fixture.csv'), check_dtype=False)
pd.testing.assert_frame_equal(frame, pd.read_excel(root / 'fixture.xlsx'), check_dtype=False)
pd.testing.assert_frame_equal(frame, pq.read_table(root / 'fixture.parquet').to_pandas(), check_dtype=False)
assert duckdb.sql('select sum(value) from frame').fetchone()[0] == 6
assert BeautifulSoup('<p>fixture</p>', 'lxml').p.get_text() == 'fixture'
assert etree.fromstring(b'<root><x>fixture</x></root>').xpath('string(x)') == 'fixture'
assert fuzz.ratio('recovery', 'recovery') == 100
assert scipy.stats.norm.cdf(0) == 0.5
assert np.allclose(np.array([1, 2, 3]) * 2, [2, 4, 6])
assert list(tqdm(range(3), disable=True)) == [0, 1, 2]
db = sqlite_utils.Database(root / 'fixture.sqlite')
db['values'].insert_all(frame.to_dict('records'), replace=True, pk='name')
assert db['values'].count == 3
with httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, json={'fixture': True}))) as client:
    assert client.get('https://example.invalid/').json() == {'fixture': True}
figure = go.FigureWidget(data=[go.Scatter(x=[1, 2, 3], y=[2, 4, 6])])
assert len(figure.data[0].x) == 3
figure.to_json()
plt.plot(frame['value'], frame['value'] ** 2)
plt.title('Recovery fixture')
plt.savefig(root / 'fixture.png')
plt.savefig(root / 'fixture.pdf')
with pdfplumber.open(root / 'fixture.pdf') as pdf:
    assert len(pdf.pages) == 1
    assert 'Recovery fixture' in pdf.pages[0].extract_text()
assert (root / 'fixture.png').read_bytes().startswith(bytes([137, 80, 78, 71]))
assert not any(str(Path.home() / '.local/lib/python') in path for path in sys.path)
print(json.dumps({'python': sys.version.split()[0], 'numpy': np.__version__, 'pandas': pd.__version__,
                  'dataRoundtrips': True, 'chartAndPdf': True, 'plotlyWidget': True}))
plt.show()
'''
notebook = nbformat.v4.new_notebook(cells=[nbformat.v4.new_code_cell(code)])
notebook.metadata.kernelspec = {'name': 'python3', 'display_name': 'Python 3 (Home Manager)', 'language': 'python'}
executed = NotebookClient(notebook, timeout=180, kernel_name='python3', resources={'metadata': {'path': str(root)}}).execute()
nbformat.write(executed, root / 'executed.ipynb')
outputs = executed.cells[0].outputs
assert any('image/png' in output.get('data', {}) for output in outputs), 'No inline plot output'
for output in outputs:
    if output.get('output_type') == 'stream':
        print(output['text'], end='')
print('HM_RESTORE_NOTEBOOK_EXECUTED_WITH_INLINE_CHART')
