import { render, screen } from '@testing-library/react';
import App from './App';

jest.mock('./pages/DashboardPage/dashboard', () => () => <h1>Connected dashboard</h1>);
jest.mock('./pages/HomePage/home', () => () => <h1>Welcome</h1>);
jest.mock('./pages/SituationPage/situation', () => () => <h1>Situation</h1>);
jest.mock('./pages/ResultPage/result', () => () => <h1>Result</h1>);
jest.mock('./pages/PreviewPage/preview', () => () => <h1>Mock preview</h1>);

test.each([
  ['/', 'Connected dashboard'],
  ['/dashboard', 'Connected dashboard'],
  ['/preview', 'Mock preview'],
  ['/welcome', 'Welcome'],
  ['/situation', 'Situation'],
  ['/result', 'Result'],
])('%s renders the intended screen', (path, heading) => {
  window.history.replaceState({}, '', path);
  render(<App />);
  expect(screen.getByRole('heading', {name: heading})).toBeInTheDocument();
});
