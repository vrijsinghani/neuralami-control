import { ThemeProvider } from '@mui/material/styles';
import { CssBaseline } from '@mui/material';
import theme from './theme';
import ThemeDemo from './components/ThemeDemo';

function App() {
  return (
    <ThemeProvider theme={theme}>
      <CssBaseline />
      <div style={{ 
        padding: '48px 24px',
        minHeight: '100vh',
        background: theme.palette.background.default
      }}>
        <ThemeDemo />
      </div>
    </ThemeProvider>
  );
}

export default App;