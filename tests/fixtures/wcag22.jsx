import React from 'react';
import { IconButton, Dialog } from '@mui/material';
import DeleteIcon from '@mui/icons-material/Delete';
import { AgGridReact } from 'ag-grid-react';

export default function Page() {
  return (
    <main>
      <h1>Account</h1>
      <style>{`
        .bar { position: sticky; top: 0; }
        .spin { animation: spin 1s infinite; }
        @keyframes spin { to { transform: rotate(360deg); } }
        @media (orientation: portrait) { .wide { display: none; } }
      `}</style>
      <div className="bar" style={{ position: "sticky", top: 0 }}>Sticky header</div>
      <button style={{ width: 16, height: 16 }}>x</button>
      <button style={{ width: 44, height: 44 }}>ok</button>
      <div onClick={go}>Clickable div</div>
      <div onClick={go} role="button" tabIndex={0} onKeyDown={go}>Keyboard div</div>
      <IconButton onClick={go}><DeleteIcon /></IconButton>
      <IconButton aria-label="Delete" onClick={go}><DeleteIcon /></IconButton>
      <Dialog open>Unnamed</Dialog>
      <Dialog open aria-labelledby="t">Named</Dialog>
      <input type="password" autoComplete="off" />
      <input type="text" name="email" />
      <input type="text" name="email" autoComplete="email" />
      <input type="text" name="note" onPaste={block} />
      <div draggable="true">Drag me</div>
      <div className="toast">Saved</div>
      <div className="toast" role="status">Saved</div>
      <div className="g-recaptcha" />
      <div onMouseEnter={show}>Hover tip</div>
      <div style={{ height: 20, overflow: 'hidden' }}>Clipped text</div>
      <AgGridReact rowData={rows} />
    </main>
  );
}
