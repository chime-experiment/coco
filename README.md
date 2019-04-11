# coco
A Config Controller

> In colloquial Spanish and Portuguese, *coco* means head or mind.  
> The fruit was apparently named by sailors who were reminded of a bogeyman called *coco* by the three holes in the shell. *coco* comes to get or eat misbehaving children.

## Overview
*coco* keeps a number of hosts organized in groups.
Using YAML files *endpoints* can be defined to be exposed or called on specified conditions. The call of an endpoint results in *coco* calling the same endpoint on a given set of hosts. *coco* can be configured to check or compare the results and based on that export [prometheus](prometheus.io) alerts, write [slack](slack.com) messages or call other endpoints.
The values passed to *endpoints* can be marked as part of a global state, which is tracked and kept in sync on the hosts.

> *Duérmete niño, duérmete ya...*  
> *Que viene el Coco y te comerá.*
