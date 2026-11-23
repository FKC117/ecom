import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import Home from './Home.jsx'
import Invoice from './Invoice.jsx'
import Control from './control/Control.jsx'
import Account from './Account.jsx'
import ParcelLabel from './control/ParcelLabel.jsx'

createRoot(document.getElementById('root')).render(
  <StrictMode>
    {window.location.pathname.startsWith('/parcel-label/') ? <ParcelLabel /> : window.location.pathname.startsWith('/invoice/') ? <Invoice /> : window.location.pathname.startsWith('/control') ? <Control /> : ["/login/", "/account/"].includes(window.location.pathname) ? <Account /> : <Home />}
  </StrictMode>,
)
