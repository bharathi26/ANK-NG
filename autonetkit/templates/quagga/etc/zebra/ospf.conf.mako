hostname ${node}
password ${node.zebra.password}   
banner motd file /etc/quagga/motd.txt
!
% for interface in node.interfaces:  
  interface ${interface.id}
  #Link to ${interface.description}
  ip ospf cost ${interface.ospf_cost}
  !
%endfor
!
% if node.ospf: 
router ospf
% for ospf_link in node.ospf.ospf_links:
  network ${ospf_link.network.cidr} area ${ospf_link.area} 
% endfor    
% endif           
!
