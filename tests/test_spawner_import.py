import sys, unittest
from pathlib import Path
import numpy as np
sys.path.insert(0,r'C:\Users\FinnStetter\Documents\XimajRoboSim\ximaj_robosim')
import sim, vcmx_import
from kinematics import pose_to_mat
class SpawnerImport(unittest.TestCase):
    def test_creator_local_offset_rotates_with_component(self):
        m=pose_to_mat(100,200,10,90,0,0)
        o=vcmx_import._parametric('Creator','spawner',{'Length_X':'200','Width_Y':'500','Height_Z':'800','Creator::Interval':'2'},m,[],1)
        np.testing.assert_allclose(o.pos,(m @ np.array([200,250,800,1]))[:3])
        self.assertEqual(o.interval,2)
    def test_untitled_creates_and_transports_multiple_parts(self):
        p=Path(r'C:\Users\FinnStetter\OneDrive - Ximaj IT-Solutions GmbH\Dokumente\KUKA\iiQWorks.Sim 1.3\My Models\Untitled.vcmx')
        if not p.exists(): self.skipTest('Lokale Testdatei fehlt')
        s=sim.Simulation(); vcmx_import.import_file(s,str(p))
        creator=next(o for o in s.scene if o.kind=='spawner')
        self.assertEqual(creator.interval,2)
        self.assertEqual(creator.part_size,[200,100,200])
        # Der Creator haengt an $OUT[1] des Roboters (CreationSignal): Programm laufen lassen
        s.start_all()
        for _ in range(400): s.tick(.1)
        parts=[o for o in s.scene if o.name.startswith(creator.name+'_teil')]
        print('Spawner:',creator.pos,'Teile:',creator.spawned,'Positionen:',[o.pos for o in parts])
        self.assertGreaterEqual(creator.spawned,4)
        self.assertTrue(any(np.linalg.norm(np.array(o.pos[:2])-creator.pos[:2])>500 for o in parts))
        self.assertTrue(any(o.pos[2]>=799 for o in parts))   # Teile laufen auf Bandhoehe (am Bandende fallen sie herunter)
if __name__=='__main__': unittest.main()
