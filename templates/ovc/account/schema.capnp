
@0x847d3d929f720fdd;
struct Schema {
	description @0 :Text;
	g8client @1 :Text;
	accountusers @2 :List(Text);
	accountID @3 :Int64 = 0;
	maxMemoryCapacity @4 :Int64 = -1;
	maxCPUCapacity @5 :Int64 = -1;
	maxNumPublicIP @6 :Int64 = -1;
	maxDiskCapacity @7 :Int64 = -1;

}
