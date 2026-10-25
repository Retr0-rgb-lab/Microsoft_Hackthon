import type { Camera, Vector3 } from "three";

declare module "three/addons/controls/OrbitControls.js" {
  export class OrbitControls {
    constructor(object: Camera, domElement?: HTMLElement);
    enabled: boolean;
    target: Vector3;
    enablePan: boolean;
    enableDamping: boolean;
    enableRotate: boolean;
    minDistance: number;
    maxDistance: number;
    minPolarAngle: number;
    maxPolarAngle: number;
    update(): boolean;
    dispose(): void;
  }
}
