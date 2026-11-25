import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import Menu from './screens/Menu/Menu';
import Manager from './screens/Manager/Manager';
import Chef from './screens/Chef/Chef';
import Waiter from './screens/Waiter/Waiter';
import LoginScreen from './screens/LoginScreen/LoginScreen';
import PaymentResult from './screens/PaymentResult';
import MockGateway from './screens/MockGateway/MockGateway';
import { getAccessToken, getRole } from './services/api';

function Private({children}) { return getAccessToken() ? children : <Navigate to="/login" replace/>; }
function AdminOnly({children}) { return getRole() === 'AD' ? children : <Navigate to="/manager" replace/>; }
export default function App(){
 return <BrowserRouter><Routes>
  <Route path="/" element={<Navigate to="/menu?table=12" replace/>}/>
  <Route path="/menu" element={<Menu/>}/>
  <Route path="/table/:tableId" element={<Menu/>}/>
  <Route path="/login" element={<LoginScreen/>}/>
  <Route path="/payment-result" element={<PaymentResult/>}/>
  <Route path="/payment/mock" element={<MockGateway/>}/>
  <Route path="/manager" element={<Private><Manager/></Private>}/>
  <Route path="/manager/settings" element={<Private><AdminOnly><Manager initialNav="settings"/></AdminOnly></Private>}/>
  <Route path="/chef" element={<Private><Chef/></Private>}/>
  <Route path="/waiter" element={<Private><Waiter/></Private>}/>
  <Route path="/staff" element={<Private><Waiter/></Private>}/>
  <Route path="*" element={<Navigate to="/menu?table=12" replace/>}/>
 </Routes></BrowserRouter>;
}
