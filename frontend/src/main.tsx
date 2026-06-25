import React from 'react'
import ReactDOM from 'react-dom/client'
import { ConfigProvider, theme as antdTheme } from 'antd'
import viVN from 'antd/locale/vi_VN'
import App from './App'
import './index.css'

const theme = {
  token: {
    colorPrimary: '#005d5d',
    colorInfo: '#005d5d',
    borderRadius: 10,
    fontFamily: "'IBM Plex Sans', system-ui, sans-serif",
    colorBgLayout: '#f4f6f6',
  },
  algorithm: antdTheme.defaultAlgorithm,
}

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <ConfigProvider theme={theme} locale={viVN}>
      <App />
    </ConfigProvider>
  </React.StrictMode>,
)
