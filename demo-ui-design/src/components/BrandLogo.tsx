interface BrandLogoProps {
  className?: string;
}

export default function BrandLogo({ className = '' }: BrandLogoProps) {
  return (
    <img
      src="/v2/htc_global_services_20260326.PNG"
      alt="HTC Global Services"
      className={`h-10 w-auto object-contain ${className}`.trim()}
    />
  );
}
