import ank
import itertools
import netaddr

#TODO: for any property not in nidb, try and pass through to obtain from respective overlay, eg ospf tries from G_ospf.node(node) etc

def dict_to_sorted_list(data, sort_key):
    """Returns values in dict, sorted by sort_key"""
    return sorted(data.values(), key = lambda x: x[sort_key])

class RouterCompiler(object):
    def __init__(self, nidb, anm):
        self.nidb = nidb
        self.anm = anm

    def compile(self, node):
        node.interfaces = dict_to_sorted_list(self.interfaces(node), 'id')
        if node in self.anm.overlay.ospf:
            node.ospf.ospf_links = dict_to_sorted_list(self.ospf(node), 'network')
        
        if node in self.anm.overlay.bgp:
            bgp_data = self.bgp(node)
            node.bgp.ibgp_rr_clients = dict_to_sorted_list(bgp_data['ibgp_rr_clients'], 'neighbor')
            node.bgp.ibgp_rr_parents = dict_to_sorted_list(bgp_data['ibgp_rr_parents'], 'neighbor')
            node.bgp.ibgp_neighbors = dict_to_sorted_list(bgp_data['ibgp_neighbors'], 'neighbor')
            node.bgp.ebgp_neighbors = dict_to_sorted_list(bgp_data['ebgp_neighbors'], 'neighbor')

    def interfaces(self, node):
        phy_node = self.anm.overlay.phy.node(node)
        G_ip = self.anm.overlay.ip
        interfaces = {}
        for link in phy_node.edges():
            ip_link = G_ip.edge(link)
            nidb_edge = self.nidb.edge(link)
            #TODO: what if multiple ospf costs for this link
            subnet =  ip_link.dst.subnet # netmask comes from collision domain on the link
            interfaces[link] = {
                    'id': nidb_edge.id,
                    'description': "%s to %s" % (link.src, link.dst),
                    'ip_address': link.overlay.ip.ip_address,
                    'subnet': subnet,
                    }

        return interfaces

    def ospf(self, node):
        """Returns OSPF links
        Also sets process_id
        """
        G_ospf = self.anm.overlay.ospf
        phy_node = self.anm.overlay.phy.node(node)
        node.ospf.process_id = 1
        ospf_links = {}
        for link in G_ospf.edges(phy_node):
            ospf_links[link] = {
                'network': link.overlay.ip.dst.subnet,
                'area': link.area,
                }
        return ospf_links

    def bgp(self, node):
        phy_node = self.anm.overlay.phy.node(node)
        G_bgp = self.anm.overlay.bgp
        G_ip = self.anm.overlay.ip
        asn = phy_node.asn # easy reference for cleaner code
        node.bgp.advertise_subnets = G_ip.data.asn_blocks[asn]
        ibgp_neighbors = {}
        ibgp_rr_clients = {}
        ibgp_rr_parents = {}
        ebgp_neighbors = {}

        for session in G_bgp.edges(phy_node):
            neigh = session.dst
            key = str(neigh) # used to index dict for sorting
            neigh_ip = G_ip.node(neigh)
            if session.type == "ibgp":
                #print session.direction
                data = {
                    'neighbor': neigh,
                    'loopback': neigh_ip.loopback,
                    'update_source': "loopback 0",
                    }
                if session.direction == 'down':
                    ibgp_rr_clients[key] = data
                elif session.direction == 'up':
                    ibgp_rr_parents[key] = data
                else:
                    ibgp_neighbors[key] = data
            else:
                ebgp_neighbors[key] = {
                    'neighbor': neigh,
                    'loopback': neigh_ip.loopback,
                    'update_source': "loopback 0",
                }

        return {
                'ibgp_rr_clients':  ibgp_rr_clients,
                'ibgp_rr_parents': ibgp_rr_parents,
                'ibgp_neighbors': ibgp_neighbors,
                'ebgp_neighbors': ebgp_neighbors,
                }

class IosCompiler(RouterCompiler):

    def interfaces(self, node):
        ip_node = self.anm.overlay.ip.node(node)
        loopback_subnet = netaddr.IPNetwork("0.0.0.0/32")

        interfaces = super(IosCompiler, self).interfaces(node)
        # OSPF cost
        for link in interfaces:
            interfaces[link]['ospf cost'] = link.overlay.ospf.cost

        interfaces['lo0'] = {
            'id': 'lo0',
            'description': "Loopback",
            'ip_address': ip_node.loopback,
            'subnet': loopback_subnet,
            }

        return interfaces

class JunosCompiler(RouterCompiler):
    pass


# Platform compilers
class PlatformCompiler(object):
# and set properties in nidb._graph.graph
    def __init__(self, nidb, anm, host):
        self.nidb = nidb
        self.anm = anm
        self.host = host

    def compile(self):
        #TODO: make this abstract
        pass

class JunosphereCompiler(PlatformCompiler):
    def interface_ids(self):
        invalid = set([2])
        valid_ids = (x for x in itertools.count(0) if x not in invalid)
        for x in valid_ids:
            yield "ge-0/0/%s" % x

    def compile(self):
        print "compiling dynagen for", self.host
        G_phy = self.anm.overlay.phy
        junos_compiler = JunosCompiler(self.nidb, self.anm)
        for phy_node in G_phy.nodes('is_router', host = self.host, syntax='junos'):
            nidb_node = self.nidb.node(phy_node)
            nidb_node.render.template = "templates/junos.mako"
            nidb_node.render.dst_folder = "rendered/junos"
            nidb_node.render.dst_file = "%s.conf" % ank.name_folder_safe(phy_node.label)

            int_ids = self.interface_ids()
            for edge in self.nidb.edges(nidb_node):
                edge.id = int_ids.next()

            junos_compiler.compile(nidb_node)

class NetkitCompiler(PlatformCompiler):
    pass

class DynagenCompiler(PlatformCompiler):
    def interface_ids(self):
        for x in itertools.count(0):
            yield "gigabitethernet0/0/0/%s" % x

    def compile(self):
        print "compiling dynagen for", self.host
        G_phy = self.anm.overlay.phy
        ios_compiler = IosCompiler(self.nidb, self.anm)
        for phy_node in G_phy.nodes('is_router', host = self.host, syntax='ios'):
            nidb_node = self.nidb.node(phy_node)
            nidb_node.render.template = "templates/ios.mako"
            nidb_node.render.dst_folder = "rendered/ios"
            nidb_node.render.dst_file = "%s.conf" % ank.name_folder_safe(phy_node.label)

            # Allocate edges
            # assign interfaces
            # Note this could take external data
            int_ids = self.interface_ids()
            for edge in self.nidb.edges(nidb_node):
                edge.id = int_ids.next()

            ios_compiler.compile(nidb_node)

